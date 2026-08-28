// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project;

import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.project.Project;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.util.Optional;

/**
 * Makes sure a single-tenant installation has the one project it is allowed to have.
 *
 * <p>This runs on every start and is idempotent: the second start finds the project the first
 * one created and changes nothing. That matters more than it sounds, because the alternative —
 * provisioning as a one-off migration — makes restoring a database backup into a state where the
 * row exists but the marker saying it exists does not.
 *
 * <p>The class takes a {@link Clock} rather than calling {@code Instant.now()} so its test can
 * assert on the timestamp it wrote. It takes no framework types at all, which is why that test
 * is plain JUnit with a hand-written repository and no application context.
 */
public class ProjectProvisioning {

    /**
     * The slug of the project a single-tenant install gets. It is never shown and never typed;
     * it exists so the row can be found again by something other than "the only one".
     */
    public static final Slug DEFAULT_PROJECT_SLUG = new Slug("default");

    public static final String DEFAULT_PROJECT_NAME = "Default";

    private final ProjectRepository projects;
    private final TenancyMode mode;
    private final Clock clock;

    public ProjectProvisioning(ProjectRepository projects, TenancyMode mode, Clock clock) {
        this.projects = projects;
        this.mode = mode;
        this.clock = clock;
    }

    /**
     * Creates the default project if this is a single-tenant install and it does not exist yet.
     *
     * @return the default project in single-tenant mode, empty in multi-tenant mode where
     *     projects are created explicitly and provisioning one implicitly would be wrong
     */
    public Optional<Project> provisionDefaultProject() {
        if (mode != TenancyMode.SINGLE) {
            return Optional.empty();
        }

        Optional<Project> existing = projects.findBySlug(DEFAULT_PROJECT_SLUG);
        if (existing.isPresent()) {
            return existing;
        }

        // A single-tenant install that already holds a project under a different slug is not
        // something to quietly add a second project to. It means the mode was switched, or the
        // database belongs to something else, and both deserve a failed start.
        long existingProjects = projects.count();
        if (existingProjects > 0) {
            throw new IllegalStateException(
                    "tenancy mode is 'single' but the database already holds " + existingProjects
                            + " project(s), none of them '" + DEFAULT_PROJECT_SLUG + "'. Refusing"
                            + " to add another. Set LUDUS_TENANCY_MODE=multi or point at the"
                            + " right database.");
        }

        Project created =
                Project.create(DEFAULT_PROJECT_SLUG, DEFAULT_PROJECT_NAME, clock.instant());
        return Optional.of(projects.save(created));
    }
}
