// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface AudioClipJpaRepository extends JpaRepository<AudioClipEntity, UUID> {

    Optional<AudioClipEntity> findByProjectIdAndId(UUID projectId, UUID id);

    List<AudioClipEntity> findByProjectIdOrderByCreatedAtDesc(UUID projectId);

    long deleteByProjectIdAndId(UUID projectId, UUID id);
}
