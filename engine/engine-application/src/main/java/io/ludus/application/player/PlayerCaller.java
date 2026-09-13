// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;

/**
 * A game client acting as one player.
 *
 * <p>A separate type from {@code Caller}, not another {@code Kind} on it. {@code Caller} carries a
 * {@link io.ludus.domain.identity.Role} and requires one, and a player has none — there is no role
 * that means "may edit exactly their own player state and nothing else". Squeezing a player in as a
 * {@code VIEWER} would make every route that checks {@code hasRole("VIEWER")} reachable by anybody
 * holding a shipped API key, which is precisely the boundary the player token exists to draw.
 *
 * <p>It carries the player id, and that id is the <em>only</em> player any request bearing this
 * principal may read or write. That is checked in the use cases rather than trusted from a path
 * parameter: a route of the shape {@code /players/{id}/currency} authorised by "is a player" is a
 * route where any player can write any other player's balance.
 */
public record PlayerCaller(PlayerId id, ProjectId projectId) {

    public PlayerCaller {
        if (id == null || projectId == null) {
            throw new IllegalArgumentException("a player caller is missing a required field");
        }
    }

    @Override
    public String toString() {
        return "PLAYER:" + id;
    }
}
