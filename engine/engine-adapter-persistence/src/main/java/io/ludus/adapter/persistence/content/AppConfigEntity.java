// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.domain.content.AppConfig;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.project.ProjectId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * The stored shape of a project's configuration.
 *
 * <p>The generated {@code config} jsonb column is not mapped, exactly as on {@link WaveEntity}:
 * mapping it would invite something to read the document back through a normalising path, and the
 * ETag is a hash of the bytes in {@code config_json}.
 */
@Entity
@Table(name = "app_config")
class AppConfigEntity {

    @Id
    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "config_json", nullable = false)
    private String configJson;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected AppConfigEntity() {
        // for JPA
    }

    static AppConfigEntity from(AppConfig config) {
        AppConfigEntity entity = new AppConfigEntity();
        entity.projectId = config.projectId().value();
        entity.configJson = config.body().json();
        entity.updatedAt = config.updatedAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    AppConfig toDomain() {
        return new AppConfig(new ProjectId(projectId), new ContentBody(configJson), updatedAt);
    }
}
