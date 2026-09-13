// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.Leaderboards;
import io.ludus.application.player.PlayerCaller;
import io.ludus.application.player.port.in.CurrentPlayer;
import io.ludus.application.player.port.out.LeaderboardRepository;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
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
 * Reading a board, and submitting to it as the player the token names.
 *
 * <p>Under {@code /api/v1/player}, so a player session token is required — and the score recorded is
 * always theirs. There is no route that writes another player's score, for the same reason there is
 * no route that reads another player's profile: with no id in the path, there is nothing to forget
 * to check.
 *
 * <p><b>A player may submit their own score, unlike currency, which only an editor may grant.</b>
 * That is not an inconsistency. A forged score is cheating, and a client-fed leaderboard can always
 * be cheated — the engine cannot tell a real lap time from an invented one, and no credential design
 * changes that. Requiring a server credential would stop the games that have no server and
 * inconvenience nobody else. A leaderboard fed by clients is a leaderboard of what clients claimed,
 * and the documentation says so.
 */
@RestController
@RequestMapping("/api/v1/player/leaderboards")
@Tag(name = "Leaderboards")
class LeaderboardController {

    private final Leaderboards leaderboards;
    private final CurrentPlayer currentPlayer;

    LeaderboardController(Leaderboards leaderboards, CurrentPlayer currentPlayer) {
        this.leaderboards = leaderboards;
        this.currentPlayer = currentPlayer;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "listLeaderboards", summary = "Every board this project defines")
    List<LeaderboardDtos.BoardView> list() {
        PlayerCaller player = currentPlayer.require();
        return leaderboards.list(player.projectId()).stream()
                .map(LeaderboardDtos.BoardView::of)
                .toList();
    }

    @GetMapping(path = "/{boardId}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getLeaderboardPage",
            summary = "A page of a board, in rank order",
            description =
                    "Cursor-paged. A row whose score does not change is returned exactly once"
                            + " across a walk, however many other scores are written meanwhile; a"
                            + " row whose score does change may move. There is no page number,"
                            + " deliberately.")
    ResponseEntity<LeaderboardDtos.PageView> page(
            @PathVariable String boardId,
            @RequestParam(required = false) String cursor,
            @RequestParam(required = false) Integer limit) {

        PlayerCaller player = currentPlayer.require();
        return board(boardId)
                .map(
                        id ->
                                ResponseEntity.ok(
                                        LeaderboardDtos.PageView.of(
                                                leaderboards.page(
                                                        player.projectId(),
                                                        id,
                                                        parseCursor(cursor),
                                                        limit == null ? 20 : limit))))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping(path = "/{boardId}/me", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getOwnLeaderboardEntry",
            summary = "Where this player sits on a board",
            description = "404 when they have not scored on it.")
    ResponseEntity<LeaderboardDtos.EntryView> me(@PathVariable String boardId) {
        PlayerCaller player = currentPlayer.require();
        return board(boardId)
                .flatMap(id -> leaderboards.entryOf(player.projectId(), id, player.id()))
                .map(entry -> ResponseEntity.ok(LeaderboardDtos.EntryView.of(entry)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(path = "/{boardId}/me", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "submitOwnScore",
            summary = "Record this player's score",
            description =
                    "The better of the new score and the existing one is kept, in the board's own"
                            + " direction. Always this player: there is no route that writes"
                            + " another's.")
    LeaderboardDtos.EntryView submit(
            @PathVariable String boardId,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    LeaderboardDtos.ScoreRequest request) {

        PlayerCaller player = currentPlayer.require();
        Slug id =
                board(boardId)
                        .orElseThrow(
                                () ->
                                        new ContentRejected(
                                                List.of(
                                                        new ContentViolation(
                                                                "/boardId",
                                                                "'" + boardId + "' is not a board id"))));
        if (request == null || request.score() == null) {
            throw new ContentRejected(List.of(new ContentViolation("/score", "send a score")));
        }

        leaderboards.submit(player.projectId(), id, player.id(), request.score());
        return LeaderboardDtos.EntryView.of(
                leaderboards.entryOf(player.projectId(), id, player.id()).orElseThrow());
    }

    private Optional<Slug> board(String candidate) {
        return Slug.isValid(candidate) ? Optional.of(new Slug(candidate)) : Optional.empty();
    }

    /**
     * The cursor a previous page returned.
     *
     * <p>A mangled one starts from the beginning rather than failing: it can only have come from a
     * response, so a bad one means a client damaged it, and the first page is a more useful answer
     * than an error about an opaque token.
     */
    private LeaderboardRepository.Cursor parseCursor(String cursor) {
        if (cursor == null || cursor.isBlank()) {
            return null;
        }
        int separator = cursor.indexOf(':');
        if (separator <= 0) {
            return null;
        }
        try {
            return new LeaderboardRepository.Cursor(
                    Long.parseLong(cursor.substring(0, separator)),
                    PlayerId.of(cursor.substring(separator + 1)));
        } catch (IllegalArgumentException malformed) {
            return null;
        }
    }
}
