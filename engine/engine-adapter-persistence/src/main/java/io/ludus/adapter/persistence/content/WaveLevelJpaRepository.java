// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface WaveLevelJpaRepository extends JpaRepository<WaveLevelEntity, UUID> {

    // Every finder names project_id, and there is deliberately no finder without it: a level
    // looked up by id alone would be readable from any project that guessed one.
    Optional<WaveLevelEntity> findByIdAndProjectId(UUID id, UUID projectId);

    List<WaveLevelEntity> findByProjectIdOrderByNameAsc(UUID projectId);

    long deleteByIdAndProjectId(UUID id, UUID projectId);
}
