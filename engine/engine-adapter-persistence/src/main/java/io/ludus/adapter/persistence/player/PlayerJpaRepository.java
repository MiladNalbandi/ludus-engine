// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.domain.Limit;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface PlayerJpaRepository extends JpaRepository<PlayerEntity, UUID> {

    Optional<PlayerEntity> findByIdAndProjectId(UUID id, UUID projectId);

    Optional<PlayerEntity> findByProjectIdAndExternalId(UUID projectId, String externalId);

    long countByProjectId(UUID projectId);

    long deleteByIdAndProjectId(UUID id, UUID projectId);

    List<PlayerEntity> findByProjectIdOrderByLastSeenAtDescIdDesc(UUID projectId, Limit limit);

    /**
     * The page after a given row, by keyset.
     *
     * <p>The id is part of the comparison because {@code last_seen_at} is not unique — two players
     * seen in the same microsecond would otherwise either both appear on two pages or neither
     * appear on any.
     */
    @Query("""
            select p from PlayerEntity p
             where p.projectId = :projectId
               and (p.lastSeenAt < :lastSeenAt
                    or (p.lastSeenAt = :lastSeenAt and p.id < :id))
             order by p.lastSeenAt desc, p.id desc
            """)
    List<PlayerEntity> pageAfter(
            @Param("projectId") UUID projectId,
            @Param("lastSeenAt") Instant lastSeenAt,
            @Param("id") UUID id,
            Limit limit);
}
