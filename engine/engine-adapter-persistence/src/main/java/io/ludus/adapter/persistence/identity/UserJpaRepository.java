// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface UserJpaRepository extends JpaRepository<UserEntity, UUID> {

    // Every finder names project_id first. A derived query missing it would compile and would
    // return another project's user, so there is deliberately no finder here without it.
    Optional<UserEntity> findByProjectIdAndEmail(UUID projectId, String email);

    Optional<UserEntity> findByProjectIdAndId(UUID projectId, UUID id);

    long countByProjectId(UUID projectId);
}
