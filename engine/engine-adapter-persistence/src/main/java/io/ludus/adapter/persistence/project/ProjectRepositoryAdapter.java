// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.project;

import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/** Implements the application's {@link ProjectRepository} on top of JPA. */
@Repository
public class ProjectRepositoryAdapter implements ProjectRepository {

    private final ProjectJpaRepository projects;

    ProjectRepositoryAdapter(ProjectJpaRepository projects) {
        this.projects = projects;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Project> findById(ProjectId id) {
        return projects.findById(id.value()).map(ProjectEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Project> findBySlug(Slug slug) {
        return projects.findBySlug(slug.value()).map(ProjectEntity::toDomain);
    }

    @Override
    @Transactional
    public Project save(Project project) {
        return projects.save(ProjectEntity.from(project)).toDomain();
    }

    @Override
    @Transactional(readOnly = true)
    public long count() {
        return projects.count();
    }
}
