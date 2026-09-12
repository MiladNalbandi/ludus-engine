// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;

/**
 * A board the project defines.
 *
 * <p>{@link #descending()} belongs to the board rather than to a query. A high score and a lap time
 * are both leaderboards and they sort opposite ways; asking each caller to say which would mean two
 * callers eventually disagreeing, and a player's rank depending on who asked.
 */
public record Leaderboard(
        ProjectId projectId,
        Slug id,
        String name,
        boolean descending,
        Instant createdAt,
        Instant updatedAt) {

    public static final int MAX_NAME_LENGTH = 255;

    public Leaderboard {
        if (projectId == null) {
            throw new IllegalArgumentException("a leaderboard must belong to a project");
        }
        if (id == null) {
            throw new IllegalArgumentException("leaderboard id must not be null");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("a leaderboard needs a name");
        }
        if (name.length() > MAX_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "a leaderboard name must be at most " + MAX_NAME_LENGTH + " characters");
        }
        if (createdAt == null || updatedAt == null) {
            throw new IllegalArgumentException("a leaderboard must carry both of its timestamps");
        }
    }

    public static Leaderboard create(
            ProjectId projectId, Slug id, String name, boolean descending, Instant now) {
        return new Leaderboard(projectId, id, name, descending, now, now);
    }

    public Leaderboard with(String newName, boolean newDescending, Instant now) {
        return new Leaderboard(projectId, id, newName, newDescending, createdAt, now);
    }
}
