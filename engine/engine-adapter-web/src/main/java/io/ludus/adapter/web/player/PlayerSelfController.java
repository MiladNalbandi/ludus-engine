// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.PlayerCaller;
import io.ludus.application.player.PlayerSessions;
import io.ludus.application.player.port.in.CurrentPlayer;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
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
    private final CurrentPlayer currentPlayer;

    PlayerSelfController(PlayerSessions sessions, CurrentPlayer currentPlayer) {
        this.sessions = sessions;
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
}
