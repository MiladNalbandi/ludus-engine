// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;

/**
 * Someone who can sign in, inside exactly one project.
 *
 * <p>The project is part of the identity rather than a lookup done afterwards. A user is not a
 * global account that happens to have access somewhere; there is no such thing here as a user
 * without a project, which is what makes "which project is this request for" answerable from the
 * credential alone.
 */
public record User(
        UserId id,
        ProjectId projectId,
        EmailAddress email,
        PasswordHash passwordHash,
        Role role,
        boolean enabled,
        Instant createdAt) {

    public User {
        if (id == null) {
            throw new IllegalArgumentException("user id must not be null");
        }
        if (projectId == null) {
            throw new IllegalArgumentException("a user must belong to a project");
        }
        if (email == null) {
            throw new IllegalArgumentException("user email must not be null");
        }
        if (passwordHash == null) {
            throw new IllegalArgumentException("user password hash must not be null");
        }
        if (role == null) {
            throw new IllegalArgumentException("user role must not be null");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("user createdAt must not be null");
        }
    }

    public static User create(
            ProjectId projectId,
            EmailAddress email,
            PasswordHash passwordHash,
            Role role,
            Instant createdAt) {
        return new User(UserId.random(), projectId, email, passwordHash, role, true, createdAt);
    }

    public User withPasswordHash(PasswordHash newHash) {
        return new User(id, projectId, email, newHash, role, enabled, createdAt);
    }

    public User disabled() {
        return new User(id, projectId, email, passwordHash, role, false, createdAt);
    }
}
