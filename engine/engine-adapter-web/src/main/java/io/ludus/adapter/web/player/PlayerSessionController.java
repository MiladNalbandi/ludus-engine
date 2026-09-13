// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.PlayerSessions;
import io.ludus.application.project.port.in.ActiveProject;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Starting a player's session.
 *
 * <p>Under {@code /api/v1/public} because a game client calls it, but <b>unlike the rest of that
 * prefix it requires an API key</b> — the chain asks for {@code VIEWER}, which is what a key has.
 * Published content needs no credential because it is what every copy of the game downloads;
 * minting a credential is a different act, and requiring a key here is what gives an operator a
 * way to cut off a compromised build.
 *
 * <p>The key is not treated as proof of who the player is. It cannot be: it ships inside the
 * binary. It says which project and which build; the game vouches for the identifier, and the
 * token that comes back is scoped to that one player.
 */
@RestController
@RequestMapping("/api/v1/public/players")
@Tag(name = "Players")
class PlayerSessionController {

    private final PlayerSessions sessions;
    private final ActiveProject activeProject;

    PlayerSessionController(PlayerSessions sessions, ActiveProject activeProject) {
        this.sessions = sessions;
        this.activeProject = activeProject;
    }

    @PostMapping(path = "/session", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "startPlayerSession",
            summary = "Exchange the game's player identifier for a session token",
            description =
                    "Creates the player on first sight, and is idempotent: retrying after a network"
                            + " failure resolves the same player rather than making a second one."
                            + " Requires an API key. The token it returns is the only credential"
                            + " that can write this player's state, and only this player's.")
    ResponseEntity<PlayerDtos.Session> start(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    PlayerDtos.SessionRequest request) {

        String externalId = request == null ? null : request.externalId();
        if (externalId == null || externalId.isBlank()) {
            return ResponseEntity.badRequest().build();
        }

        return ResponseEntity.ok(
                PlayerDtos.Session.of(sessions.start(activeProject.id(), externalId)));
    }
}
