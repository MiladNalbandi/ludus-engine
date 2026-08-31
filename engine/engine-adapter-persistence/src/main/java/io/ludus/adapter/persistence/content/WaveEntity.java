// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * The stored shape of a wave.
 *
 * <p>Note what is <em>not</em> mapped: the generated {@code config} jsonb column. It is derived by
 * PostgreSQL from {@code config_json} and exists for indexing. Mapping it would invite something to
 * write to it, which the database would refuse — and mapping it read-only would invite something to
 * read the document back through a normalising path, which is the exact mistake the storage design
 * exists to prevent. The document is only ever read from {@code config_json}.
 */
@Entity
@Table(name = "wave")
@IdClass(WaveKey.class)
class WaveEntity {

    @Id
    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Id
    @Column(name = "wave_id", nullable = false, length = Slug.MAX_LENGTH, updatable = false)
    private String waveId;

    @Column(name = "content_type", nullable = false, length = 64)
    private String contentType;

    @Column(name = "schema_uri", nullable = false, length = 512)
    private String schemaUri;

    @Column(name = "schema_version", nullable = false)
    private int schemaVersion;

    @Column(name = "name", nullable = false, length = Wave.MAX_NAME_LENGTH)
    private String name;

    @Column(name = "wave_order", nullable = false)
    private int waveOrder;

    @Column(name = "published", nullable = false)
    private boolean published;

    @Column(name = "config_json", nullable = false)
    private String configJson;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected WaveEntity() {
        // for JPA
    }

    static WaveEntity from(Wave wave) {
        WaveEntity entity = new WaveEntity();
        entity.projectId = wave.projectId().value();
        entity.waveId = wave.id().value();
        entity.contentType = "wave";
        entity.schemaUri = wave.schemaUri();
        entity.schemaVersion = wave.schemaVersion();
        entity.name = wave.name();
        entity.waveOrder = wave.order();
        entity.published = wave.published();
        entity.configJson = wave.body().json();
        entity.createdAt = wave.createdAt().truncatedTo(ChronoUnit.MICROS);
        entity.updatedAt = wave.updatedAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    Wave toDomain() {
        return new Wave(
                new ProjectId(projectId),
                new Slug(waveId),
                name,
                waveOrder,
                schemaVersion,
                schemaUri,
                published,
                new ContentBody(configJson),
                createdAt,
                updatedAt);
    }
}
