// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface WaveJpaRepository extends JpaRepository<WaveEntity, WaveKey> {

    // Every finder names project_id first, and there is deliberately no finder without it.
    Optional<WaveEntity> findByProjectIdAndWaveId(UUID projectId, String waveId);

    List<WaveEntity> findByProjectIdOrderByWaveOrderAsc(UUID projectId);

    List<WaveEntity> findByProjectIdAndPublishedTrueOrderByWaveOrderAsc(UUID projectId);

    /**
     * Orders held by other waves. The exclusion is done here rather than by filtering afterwards
     * so it stays correct however many waves a project has.
     */
    @Query("""
            select w.waveOrder from WaveEntity w
             where w.projectId = :projectId
               and (:excluding is null or w.waveId <> :excluding)
            """)
    List<Integer> takenOrders(
            @Param("projectId") UUID projectId, @Param("excluding") String excluding);

    /**
     * Id and timestamp only. This backs the client poll, so it must not load a document body to
     * answer — the whole point of the poll is that it is cheap enough to call on every launch.
     */
    @Query("""
            select w.waveId, w.updatedAt from WaveEntity w
             where w.projectId = :projectId and w.published = true
            """)
    List<Object[]> publishedCatalogue(@Param("projectId") UUID projectId);

    long deleteByProjectIdAndWaveId(UUID projectId, String waveId);
}
