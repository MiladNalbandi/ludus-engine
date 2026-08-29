// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.User;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.util.Optional;

/**
 * Storage for users.
 *
 * <p>Every lookup takes a {@link ProjectId}. Not because the caller might want to scope the
 * query, but because there is no method here that can be called without scoping it — a user from
 * another project is not something this interface can express, so forgetting the filter is not a
 * mistake that compiles.
 */
public interface UserRepository {

    Optional<User> findByEmail(ProjectId projectId, EmailAddress email);

    Optional<User> findById(ProjectId projectId, UserId id);

    User save(User user);

    long countIn(ProjectId projectId);
}
