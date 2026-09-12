// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;

/**
 * The stored shape of a wave level.
 *
 * <p>The membership rows are not mapped here. They are {@link WaveLevelWaveEntity}, written and
 * read by the adapter, because letting Hibernate manage them as an ordered collection made
 * reordering a level throw a constraint violation — see that class for the specifics. The position
 * column is derived from the list's indices on the way out and discarded on the way in, so the
 * order lives in one place.
 */
@Entity
@Table(name = "wave_level")
class WaveLevelEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "name", nullable = false, length = WaveLevel.MAX_NAME_LENGTH)
    private String name;

    @Column(name = "description")
    private String description;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected WaveLevelEntity() {
        // for JPA
    }

    static WaveLevelEntity from(WaveLevel level) {
        WaveLevelEntity entity = new WaveLevelEntity();
        entity.id = level.id().value();
        entity.projectId = level.projectId().value();
        entity.name = level.name();
        entity.description = level.description();
        // Truncated to microseconds, matching WaveEntity: PostgreSQL's timestamptz keeps
        // microseconds and the JVM offers nanoseconds, so a value written and read back would
        // otherwise differ from the one in hand and fail an equality assertion.
        entity.createdAt = level.createdAt().truncatedTo(ChronoUnit.MICROS);
        entity.updatedAt = level.updatedAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    UUID id() {
        return id;
    }

    UUID projectId() {
        return projectId;
    }

    /** The membership rows are fetched by the adapter and handed in, in order. */
    WaveLevel toDomain(List<Slug> waves) {
        return new WaveLevel(
                new WaveLevelId(id),
                new ProjectId(projectId),
                name,
                description,
                waves,
                createdAt,
                updatedAt);
    }
}
