// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * Which level a project is playing.
 *
 * <p>One row per project, enforced by the primary key rather than by anything here. Making
 * {@code project_id} the key is the whole mechanism: activating a second level is an update of the
 * same row, so there is no state in which two are active and no window in which none is.
 */
@Entity
@Table(name = "wave_level_activation")
class WaveLevelActivationEntity {

    @Id
    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "wave_level_id", nullable = false)
    private UUID waveLevelId;

    @Column(name = "activated_at", nullable = false)
    private Instant activatedAt;

    protected WaveLevelActivationEntity() {
        // for JPA
    }

    static WaveLevelActivationEntity of(UUID projectId, UUID waveLevelId, Instant activatedAt) {
        WaveLevelActivationEntity entity = new WaveLevelActivationEntity();
        entity.projectId = projectId;
        entity.waveLevelId = waveLevelId;
        entity.activatedAt = activatedAt.truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    UUID waveLevelId() {
        return waveLevelId;
    }
}
