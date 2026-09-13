// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * An ordered sequence of waves, played as one level.
 *
 * <p>The order is the list order. There is no {@code position} field on anything here, because a
 * position stored alongside a list is a second source of truth for the same fact, and the two drift
 * the first time somebody reorders by editing one of them. The database does store a position
 * column, since a table has no inherent order — it is written from this list's indices and read
 * back into it, and never surfaced.
 *
 * <p><b>Whether a level is active is not on this record.</b> "Active" is a fact about a project —
 * it has at most one active level — not a property each level carries. Modelling it as a boolean
 * per level is what makes "exactly one" an invariant somebody has to maintain across rows, and
 * that invariant is the whole feature. Ask {@code WaveLevels.active(projectId)} instead.
 */
public record WaveLevel(
        WaveLevelId id,
        ProjectId projectId,
        String name,
        String description,
        List<Slug> waves,
        Instant createdAt,
        Instant updatedAt) {

    public static final int MAX_NAME_LENGTH = 255;

    public WaveLevel {
        if (id == null) {
            throw new IllegalArgumentException("wave level id must not be null");
        }
        if (projectId == null) {
            throw new IllegalArgumentException("a wave level must belong to a project");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("wave level name must not be blank");
        }
        if (name.length() > MAX_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "wave level name must be at most " + MAX_NAME_LENGTH + " characters");
        }
        if (waves == null) {
            throw new IllegalArgumentException("a wave level must carry its wave list, even empty");
        }
        // A level that lists the same wave twice has two slots that advance together and a
        // progress counter that can never be right. Rejected here rather than deduplicated,
        // because silently dropping one of an author's entries is a worse surprise than an error.
        Set<Slug> seen = new LinkedHashSet<>(waves);
        if (seen.size() != waves.size()) {
            throw new IllegalArgumentException("a wave level must not list the same wave twice");
        }
        waves = List.copyOf(waves);
        if (createdAt == null || updatedAt == null) {
            throw new IllegalArgumentException("a wave level must carry both of its timestamps");
        }
    }

    public static WaveLevel create(
            WaveLevelId id,
            ProjectId projectId,
            String name,
            String description,
            List<Slug> waves,
            Instant now) {
        return new WaveLevel(id, projectId, name, description, waves, now, now);
    }

    /** A renamed or resequenced level. Identity, project and creation time survive. */
    public WaveLevel with(String newName, String newDescription, List<Slug> newWaves, Instant now) {
        return new WaveLevel(
                id, projectId, newName, newDescription, newWaves, createdAt, now);
    }
}
