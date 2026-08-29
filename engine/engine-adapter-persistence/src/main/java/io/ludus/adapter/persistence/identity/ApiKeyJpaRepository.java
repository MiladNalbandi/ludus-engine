// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface ApiKeyJpaRepository extends JpaRepository<ApiKeyEntity, UUID> {

    Optional<ApiKeyEntity> findByProjectIdAndSecretDigest(UUID projectId, String secretDigest);

    Optional<ApiKeyEntity> findByProjectIdAndId(UUID projectId, UUID id);

    List<ApiKeyEntity> findByProjectIdOrderByCreatedAtDesc(UUID projectId);
}
