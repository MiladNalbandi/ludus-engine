// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project;

import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * A hand-written stand-in for the persistence adapter.
 *
 * <p>Thirty lines, no mocking framework, no container. This is the return on keeping the
 * application layer free of Spring: the use-case tests are ordinary JUnit tests that run in
 * milliseconds, and the thing they run against is readable in one screen.
 */
class InMemoryProjectRepository implements ProjectRepository {

    private final Map<ProjectId, Project> byId = new LinkedHashMap<>();

    @Override
    public Optional<Project> findById(ProjectId id) {
        return Optional.ofNullable(byId.get(id));
    }

    @Override
    public Optional<Project> findBySlug(Slug slug) {
        return byId.values().stream().filter(p -> p.slug().equals(slug)).findFirst();
    }

    @Override
    public Project save(Project project) {
        byId.put(project.id(), project);
        return project;
    }

    @Override
    public long count() {
        return byId.size();
    }
}
