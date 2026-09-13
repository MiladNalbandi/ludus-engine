// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface WaveLevelWaveJpaRepository
        extends JpaRepository<WaveLevelWaveEntity, WaveLevelWaveKey> {

    List<WaveLevelWaveEntity> findByWaveLevelIdOrderByPositionAsc(UUID waveLevelId);

    /**
     * A bulk delete, so it reaches the database at once rather than at flush time.
     *
     * <p>That timing is the point: the rows replacing these are inserted immediately afterwards,
     * and if the delete were still pending the inserts would collide with the rows they replace.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("delete from WaveLevelWaveEntity m where m.waveLevelId = :waveLevelId")
    void deleteMembershipsOf(@Param("waveLevelId") UUID waveLevelId);
}
