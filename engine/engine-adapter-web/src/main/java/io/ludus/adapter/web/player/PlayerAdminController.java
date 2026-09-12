// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.PlayerEconomy;
import io.ludus.application.player.PlayerSessions;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * Administering players, and the only place currency can be awarded.
 *
 * <p>Editors and above. Crediting a balance is deliberately not something a game client can do:
 * an API key ships inside the binary, so a client-authorised grant makes the currency whatever a
 * modified binary says it is. A game that wants to award rewards needs a server of its own holding
 * an editor credential — a real constraint, stated rather than worked around.
 */
@RestController
@RequestMapping("/api/v1/admin/players")
@Tag(name = "Players")
class PlayerAdminController {

    /** A page size cap, so one request cannot ask for the whole table. */
    private static final int MAX_PAGE = 200;
    private static final int DEFAULT_PAGE = 50;

    private final PlayerSessions sessions;
    private final PlayerEconomy economy;
    private final PlayerRepository players;
    private final ActiveProject activeProject;

    PlayerAdminController(
            PlayerSessions sessions,
            PlayerEconomy economy,
            PlayerRepository players,
            ActiveProject activeProject) {
        this.sessions = sessions;
        this.economy = economy;
        this.players = players;
        this.activeProject = activeProject;
    }

    /**
     * A page of players, most recently seen first.
     *
     * <p>Cursor-paged, not offset-paged. {@code last_seen_at} changes every time somebody plays, so
     * an offset would skip and repeat players between pages as they do — the instability is not a
     * corner case here, it is the ordering column's normal behaviour under any traffic at all.
     */
    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "listPlayers",
            summary = "Players, most recently seen first",
            description =
                    "Cursor-paged: pass the nextCursor from the previous page. Offsets are not"
                            + " offered, because the ordering column changes on every session.")
    PlayerDtos.Page list(
            @RequestParam(required = false) String cursor,
            @RequestParam(required = false) Integer limit) {

        ProjectId project = activeProject.id();
        int size = limit == null ? DEFAULT_PAGE : Math.max(1, Math.min(MAX_PAGE, limit));

        // One more than asked for, so the presence of a next page is known without a second query.
        List<io.ludus.domain.player.Player> found =
                players.page(project, parseCursor(cursor), size + 1);

        boolean more = found.size() > size;
        List<io.ludus.domain.player.Player> page = more ? found.subList(0, size) : found;

        return new PlayerDtos.Page(
                page.stream().map(PlayerDtos.Profile::of).toList(),
                players.count(project),
                more ? encodeCursor(page.get(page.size() - 1)) : null);
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "getPlayer", summary = "One player")
    ResponseEntity<PlayerDtos.Profile> find(@PathVariable String id) {
        return parse(id)
                .flatMap(playerId -> sessions.find(activeProject.id(), playerId))
                .map(player -> ResponseEntity.ok(PlayerDtos.Profile.of(player)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping(path = "/{id}/wallet", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "getPlayerWalletAsAdmin", summary = "What a player holds")
    ResponseEntity<PlayerDtos.Wallet> wallet(@PathVariable String id) {
        return parse(id)
                .map(
                        playerId ->
                                ResponseEntity.ok(
                                        new PlayerDtos.Wallet(
                                                economy.balances(activeProject.id(), playerId).stream()
                                                        .map(PlayerDtos.BalanceView::of)
                                                        .toList())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(path = "/{id}/wallet/grant", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "grantPlayerCurrency",
            summary = "Award currency to a player",
            description =
                    "Editors and above. Not available to a game client: an API key ships inside the"
                            + " binary, so a client-authorised grant makes the currency whatever a"
                            + " modified binary says it is.")
    PlayerDtos.BalanceView grant(
            @PathVariable String id,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    PlayerDtos.GrantRequest request) {

        PlayerId playerId = parse(id).orElseThrow(PlayerAdminController::notAPlayer);
        return PlayerDtos.BalanceView.of(
                economy.grant(
                        activeProject.id(),
                        playerId,
                        PlayerCurrencies.parse(request == null ? null : request.currency()),
                        request == null || request.amount() == null ? 0 : request.amount()));
    }

    /**
     * Several currencies and XP at once, all or nothing.
     *
     * <p>This is what a reward is: forty coins, two gems and a hundred XP. A player who got the
     * coins and not the gems has been given something the game never offered, and cannot be told
     * why.
     */
    @PostMapping(path = "/{id}/reward", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "rewardPlayer",
            summary = "Award several currencies and XP together",
            description = "All or nothing: one rejected grant rolls back the whole reward.")
    PlayerDtos.RewardView reward(
            @PathVariable String id,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    PlayerDtos.RewardRequest request) {

        PlayerId playerId = parse(id).orElseThrow(PlayerAdminController::notAPlayer);
        List<PlayerEconomy.Grant> grants = new ArrayList<>();
        if (request != null && request.grants() != null) {
            for (PlayerDtos.GrantRequest grant : request.grants()) {
                grants.add(
                        new PlayerEconomy.Grant(
                                PlayerCurrencies.parse(grant == null ? null : grant.currency()),
                                grant == null || grant.amount() == null ? 0 : grant.amount()));
            }
        }

        return PlayerDtos.RewardView.of(
                economy.reward(
                        activeProject.id(),
                        playerId,
                        grants,
                        request == null || request.xp() == null ? 0 : request.xp()));
    }

    private static ContentRejected notAPlayer() {
        return new ContentRejected(
                List.of(ContentViolation.atRoot("that is not a player identifier")));
    }

    private Optional<PlayerId> parse(String id) {
        try {
            return Optional.of(PlayerId.of(id));
        } catch (IllegalArgumentException notAnId) {
            return Optional.empty();
        }
    }

    /**
     * The cursor is the previous page's last row: its timestamp and its id.
     *
     * <p>Both, because {@code last_seen_at} is not unique — two players seen in the same microsecond
     * would otherwise both appear on two pages or on neither.
     */
    private static String encodeCursor(io.ludus.domain.player.Player last) {
        return last.lastSeenAt().toEpochMilli() + ":" + last.id();
    }

    private PlayerRepository.PlayerPageCursor parseCursor(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return null;
        }
        int separator = cursor.lastIndexOf(':');
        if (separator <= 0) {
            // A malformed cursor starts from the beginning rather than failing. It can only have
            // come from a previous response, so a bad one means a client mangled it, and the first
            // page is a more useful answer than an error about an opaque token.
            return null;
        }
        try {
            return new PlayerRepository.PlayerPageCursor(
                    Instant.ofEpochMilli(Long.parseLong(cursor.substring(0, separator))),
                    PlayerId.of(cursor.substring(separator + 1)));
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }
}
