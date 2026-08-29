// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class AdministratorSeedingTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");
    private static final ProjectId PROJECT = ProjectId.random();

    private final IdentityFakes.Users users = new IdentityFakes.Users();
    private final IdentityFakes.Passwords passwords = new IdentityFakes.Passwords();
    private final AdministratorSeeding seeding =
            new AdministratorSeeding(users, passwords, Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void an_empty_project_gets_its_first_administrator() {
        User admin = seeding.seed(PROJECT, "admin@example.com", "a-real-password").orElseThrow();

        assertThat(admin.role()).isEqualTo(Role.ADMIN);
        assertThat(admin.email()).isEqualTo(new EmailAddress("admin@example.com"));
        assertThat(admin.enabled()).isTrue();
        assertThat(passwords.matches("a-real-password", admin.passwordHash())).isTrue();
    }

    /**
     * The seed configuration usually stays in place across restarts. If it kept acting, changing
     * the configured password would silently reset a real administrator's credentials, and
     * deleting an account would see it quietly reappear on the next deploy.
     */
    @Test
    void a_project_that_already_has_users_is_left_alone() {
        seeding.seed(PROJECT, "admin@example.com", "a-real-password");

        assertThat(seeding.seed(PROJECT, "someone@example.com", "another-password")).isEmpty();
        assertThat(users.countIn(PROJECT)).isEqualTo(1);
    }

    @Test
    void seeding_without_an_email_or_password_is_refused_rather_than_guessed_at() {
        assertThatIllegalArgumentException().isThrownBy(() -> seeding.seed(PROJECT, "", "pw"));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> seeding.seed(PROJECT, "admin@example.com", ""));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> seeding.seed(PROJECT, "admin@example.com", null));
    }
}
