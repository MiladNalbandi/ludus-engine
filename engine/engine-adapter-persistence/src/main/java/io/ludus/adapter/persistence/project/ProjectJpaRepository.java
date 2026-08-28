// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.project;

import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Spring Data's view of the table. Package-private on purpose: the only thing outside this
 * package that should know a project can be loaded is the outbound port.
 */
interface ProjectJpaRepository extends JpaRepository<ProjectEntity, UUID> {

    Optional<ProjectEntity> findBySlug(String slug);
}
