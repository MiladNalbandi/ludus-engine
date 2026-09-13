// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.domain.shared.Slug;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.util.UUID;

/**
 * One wave's place in one level.
 *
 * <p>An entity of its own rather than an {@code @ElementCollection} with an {@code @OrderColumn},
 * and the reason is a bug the constraint test caught. Hibernate reorders an ordered collection by
 * updating rows in place — slot 0's wave becomes 'b', slot 1's becomes 'a' — and the first of those
 * updates collides with the existing {@code (wave_level_id, wave_id)} primary key before the second
 * has run. Swapping two waves in a level threw a constraint violation.
 *
 * <p>The options were to weaken the schema (drop the key, or defer it, which PostgreSQL can do and
 * H2 cannot) or to stop letting Hibernate choose the statements. This is the second. The adapter
 * deletes a level's memberships and reinserts them, so there is no intermediate state to collide
 * in, and both constraints stay: a wave appears in a level at most once, and no two waves share a
 * slot.
 */
@Entity
@Table(name = "wave_level_wave")
@IdClass(WaveLevelWaveKey.class)
class WaveLevelWaveEntity {

    @Id
    @Column(name = "wave_level_id", nullable = false, updatable = false)
    private UUID waveLevelId;

    @Id
    @Column(name = "wave_id", nullable = false, length = Slug.MAX_LENGTH, updatable = false)
    private String waveId;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "position", nullable = false)
    private int position;

    protected WaveLevelWaveEntity() {
        // for JPA
    }

    static WaveLevelWaveEntity of(UUID waveLevelId, UUID projectId, String waveId, int position) {
        WaveLevelWaveEntity entity = new WaveLevelWaveEntity();
        entity.waveLevelId = waveLevelId;
        entity.projectId = projectId;
        entity.waveId = waveId;
        entity.position = position;
        return entity;
    }

    String waveId() {
        return waveId;
    }
}
