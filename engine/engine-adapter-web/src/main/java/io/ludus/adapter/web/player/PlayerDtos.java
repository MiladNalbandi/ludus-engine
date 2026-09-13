// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.PlayerSessions;
import io.ludus.domain.player.Player;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

final class PlayerDtos {

    private PlayerDtos() {}

    @Schema(name = "PlayerSessionRequest", description = "The game's own identifier for this player.")
    record SessionRequest(String externalId) {}

    /**
     * A session. The token is shown once per session and held in memory by the client.
     *
     * <p>The external id is echoed back so a client can confirm the engine resolved the identifier
     * it meant — a silent mismatch would show up as a player whose progress is mysteriously empty.
     */
    @Schema(name = "PlayerSession", description = "A player session token and who it acts as.")
    record Session(
            String playerId, String externalId, String displayName, String token, Instant expiresAt) {

        static Session of(PlayerSessions.Session session) {
            return new Session(
                    session.player().id().toString(),
                    session.player().externalId(),
                    session.player().displayName(),
                    session.token(),
                    session.expiresAt());
        }
    }

    /**
     * A player, as themselves or as an administrator sees them.
     *
     * <p>The external id is included, and that is a deliberate call: it is the game's own
     * identifier, which for many games is a device id. It is shown to the player it belongs to and
     * to an administrator, and to nobody else — there is no route that returns another player's
     * profile, which is why there is one DTO rather than a public and a private variant.
     */
    @Schema(name = "PlayerProfile", description = "A player's identity and when they were last seen.")
    record Profile(
            String id, String externalId, String displayName, Instant createdAt, Instant lastSeenAt) {

        static Profile of(Player player) {
            return new Profile(
                    player.id().toString(),
                    player.externalId(),
                    player.displayName(),
                    player.createdAt(),
                    player.lastSeenAt());
        }
    }

    @Schema(name = "PlayerRenameRequest", description = "A display name the player chose. Blank clears it.")
    record RenameRequest(String displayName) {}

    /**
     * A page of players, with the cursor for the next one.
     *
     * <p>A cursor rather than a page number. `last_seen_at` changes on every session, so an offset
     * would skip and repeat players as they play — the instability is not hypothetical here, it is
     * the ordering column's normal behaviour.
     */
    @Schema(name = "PlayerPage", description = "Players, most recently seen first, with a cursor.")
    record Page(List<Profile> players, long total, String nextCursor) {}
}
