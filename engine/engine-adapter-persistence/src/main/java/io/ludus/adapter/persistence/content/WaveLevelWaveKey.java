// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

/** The identity of a membership row: a wave, in a level. */
class WaveLevelWaveKey implements Serializable {

    private static final long serialVersionUID = 1L;

    private UUID waveLevelId;
    private String waveId;

    protected WaveLevelWaveKey() {
        // for JPA
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof WaveLevelWaveKey key
                && Objects.equals(waveLevelId, key.waveLevelId)
                && Objects.equals(waveId, key.waveId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(waveLevelId, waveId);
    }
}
