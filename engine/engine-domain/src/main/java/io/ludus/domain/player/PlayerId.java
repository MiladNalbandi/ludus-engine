// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import java.util.UUID;

/**
 * The engine's identifier for a player.
 *
 * <p>Distinct from the game's own identifier on purpose. Everything that refers to a player refers
 * to this, so a game that changes its identity scheme — moves from device ids to platform accounts,
 * say — migrates one column rather than every table that mentions a player.
 */
public record PlayerId(UUID value) {

    public PlayerId {
        if (value == null) {
            throw new IllegalArgumentException("player id must not be null");
        }
    }

    public static PlayerId random() {
        return new PlayerId(UUID.randomUUID());
    }

    public static PlayerId of(String value) {
        return new PlayerId(UUID.fromString(value));
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
