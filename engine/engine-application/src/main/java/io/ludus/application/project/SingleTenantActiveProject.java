// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project;

import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import java.util.concurrent.atomic.AtomicReference;

/**
 * Resolves the active project for a single-tenant install: the one created on first start.
 *
 * <p>Looked up once and then held, because the answer cannot change while the process is running
 * — a single-tenant install refuses to start if the database holds a different project, so there
 * is no second answer to switch to.
 */
public class SingleTenantActiveProject implements ActiveProject {

    private final ProjectRepository projects;
    private final TenancyMode mode;
    private final AtomicReference<ProjectId> resolved = new AtomicReference<>();

    public SingleTenantActiveProject(ProjectRepository projects, TenancyMode mode) {
        this.projects = projects;
        this.mode = mode;
    }

    @Override
    public ProjectId id() {
        ProjectId known = resolved.get();
        if (known != null) {
            return known;
        }
        if (mode != TenancyMode.SINGLE) {
            throw new IllegalStateException(
                    "tenancy mode is 'multi', so the project cannot be inferred from the"
                            + " installation. Routing a request to a project is v2.0.0 -- see"
                            + " https://github.com/MiladNalbandi/ludus-engine/issues/17");
        }
        ProjectId found =
                projects.findBySlug(ProjectProvisioning.DEFAULT_PROJECT_SLUG)
                        .map(Project::id)
                        .orElseThrow(
                                () -> new IllegalStateException(
                                        "no default project exists yet; the engine is serving"
                                                + " before provisioning completed"));
        resolved.compareAndSet(null, found);
        return resolved.get();
    }
}
