// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.PlayerCaller;
import io.ludus.application.player.ItemCatalogue;
import io.ludus.application.player.PlayerEconomy;
import io.ludus.application.player.PlayerSessions;
import io.ludus.application.player.port.in.CurrentPlayer;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * What a player may do to their own state.
 *
 * <p><b>Every route here is {@code /me}, and that is the security design rather than a naming
 * style.</b> A route of the shape {@code /players/{id}} authorised by "is a player" is a route on
 * which any player can act as any other, and the check that prevents it is one somebody has to
 * remember to write in each handler. With no id in the path there is nothing to forget: the player
 * comes from the verified token and cannot be influenced by the request.
 */
@RestController
@RequestMapping("/api/v1/player")
@Tag(name = "Players")
class PlayerSelfController {

    private final PlayerSessions sessions;
    private final PlayerEconomy economy;
    private final ItemCatalogue items;
    private final CurrentPlayer currentPlayer;

    PlayerSelfController(
            PlayerSessions sessions,
            PlayerEconomy economy,
            ItemCatalogue items,
            CurrentPlayer currentPlayer) {
        this.sessions = sessions;
        this.economy = economy;
        this.items = items;
        this.currentPlayer = currentPlayer;
    }

    @GetMapping(path = "/me", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getPlayerSelf",
            summary = "The player this token acts as",
            description = "There is no route for another player's profile, deliberately.")
    ResponseEntity<PlayerDtos.Profile> me() {
        PlayerCaller player = currentPlayer.require();
        return sessions
                .find(player.projectId(), player.id())
                .map(found -> ResponseEntity.ok(PlayerDtos.Profile.of(found)))
                // The token is valid and the row is gone: an administrator deleted the player
                // mid-session. A 404 rather than a 401, because the credential is not the problem.
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PatchMapping(path = "/me", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "renamePlayerSelf",
            summary = "Set or clear this player's display name",
            description = "Blank clears it. Names are not unique; two players may share one.")
    ResponseEntity<PlayerDtos.Profile> rename(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    PlayerDtos.RenameRequest request) {

        PlayerCaller player = currentPlayer.require();
        return sessions
                .rename(
                        player.projectId(),
                        player.id(),
                        request == null ? null : request.displayName())
                .map(renamed -> ResponseEntity.ok(PlayerDtos.Profile.of(renamed)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping(path = "/me/wallet", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getPlayerWallet",
            summary = "What this player holds",
            description = "Read-only. Awarding currency needs a credential that does not ship in the game.")
    PlayerDtos.Wallet wallet() {
        PlayerCaller player = currentPlayer.require();
        return new PlayerDtos.Wallet(
                economy.balances(player.projectId(), player.id()).stream()
                        .map(PlayerDtos.BalanceView::of)
                        .toList());
    }

    /**
     * Spends from this player's own balance.
     *
     * <p><b>A player may spend and may not be granted, and that asymmetry is the trust model.</b>
     * A forged spend costs the person who forged it, so exposing it to a client is safe. A forged
     * grant would make the currency whatever a modified binary says it is, so crediting needs a
     * credential that does not ship inside the game — see the admin route.
     *
     * <p>Refused, not clamped, when they cannot afford it.
     */
    @PostMapping(path = "/me/wallet/spend", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "spendPlayerCurrency",
            summary = "Spend from this player's balance",
            description =
                    "Refused with a 422 when the balance is insufficient, rather than clamped to"
                            + " zero. A player can spend their own currency; only an editor can"
                            + " award it.")
    PlayerDtos.BalanceView spend(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    PlayerDtos.SpendRequest request) {

        PlayerCaller player = currentPlayer.require();
        return PlayerDtos.BalanceView.of(
                economy.spend(
                        player.projectId(),
                        player.id(),
                        PlayerCurrencies.parse(request == null ? null : request.currency()),
                        request == null || request.amount() == null ? 0 : request.amount()));
    }

    @GetMapping(path = "/me/progress", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getPlayerProgress",
            summary = "This player's XP and stage",
            description = "The stage is derived from the project's curve, not stored.")
    PlayerDtos.ProgressView progress() {
        PlayerCaller player = currentPlayer.require();
        return PlayerDtos.ProgressView.of(economy.progressOf(player.projectId(), player.id()));
    }

    /**
     * What this player holds.
     *
     * <p>Read-only, like the wallet. Granting items is an editor's act for the same reason granting
     * currency is: a credential that ships inside the game cannot be trusted to say what a player
     * earned.
     */
    @GetMapping(path = "/me/inventory", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getPlayerInventory",
            summary = "What this player holds",
            description = "Read-only. Granting items needs a credential that does not ship in the game.")
    ItemDtos.Inventory inventory() {
        PlayerCaller player = currentPlayer.require();
        return new ItemDtos.Inventory(
                items.inventoryOf(player.projectId(), player.id()).stream()
                        .map(ItemDtos.EntryView::of)
                        .toList());
    }
}
