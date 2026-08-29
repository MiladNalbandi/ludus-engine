// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.application.identity.port.out.PasswordHasher;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.util.Optional;

/**
 * Creates the first administrator, so that a fresh install has someone who can sign in.
 *
 * <p>There is no default password. A fresh install with a known administrator password is a
 * fresh install that is already compromised, and the fact that the operator "should" change it
 * has never once been sufficient. The engine refuses to start without one being configured, in
 * the same way and for the same reason as the signing secret.
 *
 * <p>It seeds only into an empty project. Once a second user exists, this stops acting entirely:
 * an operator who leaves the seed configuration in place should not be quietly recreating an
 * account that someone deliberately deleted, and changing the configured password should not
 * silently reset a real administrator's credentials.
 */
public class AdministratorSeeding {

    private final UserRepository users;
    private final PasswordHasher passwords;
    private final Clock clock;

    public AdministratorSeeding(UserRepository users, PasswordHasher passwords, Clock clock) {
        this.users = users;
        this.passwords = passwords;
        this.clock = clock;
    }

    /**
     * @return the created administrator, or empty if the project already had users
     */
    public Optional<User> seed(ProjectId projectId, String email, String rawPassword) {
        if (email == null || email.isBlank() || rawPassword == null || rawPassword.isBlank()) {
            throw new IllegalArgumentException(
                    "an administrator email and password are both required to seed a project");
        }
        if (users.countIn(projectId) > 0) {
            return Optional.empty();
        }
        User admin =
                User.create(
                        projectId,
                        new EmailAddress(email),
                        passwords.hash(rawPassword),
                        Role.ADMIN,
                        clock.instant());
        return Optional.of(users.save(admin));
    }
}
