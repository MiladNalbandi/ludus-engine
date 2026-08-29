// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

interface RefreshTokenJpaRepository extends JpaRepository<RefreshTokenEntity, UUID> {

    Optional<RefreshTokenEntity> findByProjectIdAndTokenDigest(UUID projectId, String tokenDigest);

    /**
     * One statement rather than load-modify-save. Signing out of a hundred sessions should not be
     * a hundred round trips, and the set being revoked must not change underneath the operation.
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
            update RefreshTokenEntity t
               set t.revokedAt = :when
             where t.projectId = :projectId
               and t.userId = :userId
               and t.revokedAt is null
            """)
    int revokeAllFor(
            @Param("projectId") UUID projectId,
            @Param("userId") UUID userId,
            @Param("when") Instant when);
}
