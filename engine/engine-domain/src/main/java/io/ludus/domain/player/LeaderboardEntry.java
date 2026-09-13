// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import java.time.Instant;

/**
 * One player's place on a board.
 *
 * <p>{@code rank} is computed for the page being served, not stored. A stored rank is wrong for
 * everybody below the next score that changes, and the next score changes constantly.
 */
public record LeaderboardEntry(
        PlayerId playerId, String displayName, long score, long rank, Instant updatedAt) {

    public LeaderboardEntry {
        if (playerId == null) {
            throw new IllegalArgumentException("a leaderboard entry must name its player");
        }
        if (rank < 1) {
            throw new IllegalArgumentException("a rank starts at 1, was " + rank);
        }
        if (updatedAt == null) {
            throw new IllegalArgumentException("a leaderboard entry must carry its timestamp");
        }
    }
}
