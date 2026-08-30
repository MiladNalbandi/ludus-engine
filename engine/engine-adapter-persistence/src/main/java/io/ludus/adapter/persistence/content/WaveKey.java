// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

/**
 * The composite primary key, {@code (project_id, wave_id)}.
 *
 * <p>Composite rather than a surrogate uuid because the project is genuinely part of the identity:
 * two projects may each have a wave called {@code boss_rush} and they are different waves. A
 * surrogate key would permit a lookup by wave id alone, which is exactly the query that returns
 * someone else's row.
 */
class WaveKey implements Serializable {

    private static final long serialVersionUID = 1L;

    private UUID projectId;
    private String waveId;

    protected WaveKey() {
        // for JPA
    }

    WaveKey(UUID projectId, String waveId) {
        this.projectId = projectId;
        this.waveId = waveId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        return other instanceof WaveKey key
                && Objects.equals(projectId, key.projectId)
                && Objects.equals(waveId, key.waveId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(projectId, waveId);
    }
}
