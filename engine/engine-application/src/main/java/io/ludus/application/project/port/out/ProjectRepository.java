// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project.port.out;

import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.util.Optional;

/**
 * Storage for projects, in the application's vocabulary rather than the database's.
 *
 * <p>There is no {@code findAll}. Every method here is either scoped to one project or returns
 * one, which is the smallest version of the rule the rest of the schema follows: a repository
 * that can hand back rows from a project the caller did not ask for is a boundary leak waiting
 * for a careless caller. Listing projects is an administrative operation and will arrive with the
 * hosted deployment, not before.
 */
public interface ProjectRepository {

    Optional<Project> findById(ProjectId id);

    Optional<Project> findBySlug(Slug slug);

    /** Inserts or updates. Returns the stored state, which is what the caller should go on using. */
    Project save(Project project);

    /** How many projects exist. Used to decide whether a single-tenant install is provisioned. */
    long count();
}
