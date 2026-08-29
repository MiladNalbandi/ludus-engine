// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;

import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AuthenticateUserTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");
    private static final ProjectId PROJECT = ProjectId.random();
    private static final ProjectId OTHER_PROJECT = ProjectId.random();
    private static final String PASSWORD = "correct-horse-battery-staple";

    private final IdentityFakes.Users users = new IdentityFakes.Users();
    private final IdentityFakes.RefreshTokens refreshTokens = new IdentityFakes.RefreshTokens();
    private final IdentityFakes.Passwords passwords = new IdentityFakes.Passwords();
    private final IdentityFakes.Digester digester = new IdentityFakes.Digester();
    private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);

    private AuthenticateUser authenticate;

    @BeforeEach
    void setUp() {
        authenticate =
                new AuthenticateUser(
                        users,
                        refreshTokens,
                        passwords,
                        new IdentityFakes.AccessTokens(),
                        new IdentityFakes.Secrets(),
                        digester,
                        TokenLifetimes.defaults(),
                        clock);
        users.save(
                User.create(
                        PROJECT,
                        new EmailAddress("ada@example.com"),
                        passwords.hash(PASSWORD),
                        Role.EDITOR,
                        NOW));
    }

    @Test
    void the_right_password_produces_an_access_token_and_a_refresh_token() {
        IssuedTokens tokens = authenticate.authenticate(PROJECT, "ada@example.com", PASSWORD);

        assertThat(tokens.accessToken()).contains(PROJECT.toString());
        assertThat(tokens.refreshToken()).isEqualTo("secret-1");
        assertThat(tokens.accessTokenExpiresAt())
                .isEqualTo(NOW.plus(TokenLifetimes.defaults().accessToken()));
        assertThat(tokens.refreshTokenExpiresAt())
                .isEqualTo(NOW.plus(TokenLifetimes.defaults().refreshToken()));
    }

    @Test
    void the_refresh_token_is_stored_only_as_a_digest() {
        IssuedTokens tokens = authenticate.authenticate(PROJECT, "ada@example.com", PASSWORD);

        assertThat(refreshTokens.all).hasSize(1);
        assertThat(refreshTokens.all.get(0).tokenDigest().value())
                .as("the plaintext must not be recoverable from what was stored")
                .doesNotContain(tokens.refreshToken())
                .isEqualTo(digester.digest(tokens.refreshToken()).value());
    }

    @Test
    void the_address_is_matched_regardless_of_how_it_was_typed() {
        assertThat(authenticate.authenticate(PROJECT, "  ADA@Example.COM ", PASSWORD)).isNotNull();
    }

    @Test
    void a_wrong_password_is_rejected() {
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> authenticate.authenticate(PROJECT, "ada@example.com", "nope"))
                .withMessage("Authentication failed.")
                .satisfies(f -> assertThat(f.reason()).isEqualTo("password did not match"));
    }

    /**
     * The boundary, from the credential's side: the right password for the right person, against
     * the wrong project, is a failure rather than a session in someone else's data.
     */
    @Test
    void credentials_do_not_work_against_another_project() {
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(
                        () -> authenticate.authenticate(OTHER_PROJECT, "ada@example.com", PASSWORD))
                .satisfies(
                        f ->
                                assertThat(f.reason())
                                        .isEqualTo("no user with that address in this project"));
    }

    @Test
    void a_disabled_account_cannot_sign_in() {
        User ada = users.findByEmail(PROJECT, new EmailAddress("ada@example.com")).orElseThrow();
        users.save(ada.disabled());

        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> authenticate.authenticate(PROJECT, "ada@example.com", PASSWORD))
                .satisfies(f -> assertThat(f.reason()).isEqualTo("account is disabled"));
    }

    @Test
    void every_failure_tells_the_caller_exactly_the_same_thing() {
        String unknown = messageFor("nobody@example.com", PASSWORD);
        String wrongPassword = messageFor("ada@example.com", "nope");
        String malformed = messageFor("not-an-address", PASSWORD);

        assertThat(unknown).isEqualTo(wrongPassword).isEqualTo(malformed);
    }

    /**
     * Returning early for an unknown address makes it measurably faster than a wrong password,
     * and that difference alone is enough to work out who has an account here. The decoy check
     * is what removes it, so its absence is worth asserting on rather than trusting.
     */
    @Test
    void an_address_that_does_not_exist_still_costs_a_password_check() {
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(
                        () -> authenticate.authenticate(PROJECT, "nobody@example.com", PASSWORD));

        assertThat(passwords.decoyChecks).hasValue(1);
    }

    @Test
    void a_malformed_address_also_costs_a_password_check() {
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> authenticate.authenticate(PROJECT, "not-an-address", PASSWORD));

        assertThat(passwords.decoyChecks).hasValue(1);
    }

    @Test
    void an_empty_password_is_refused_without_looking_anyone_up() {
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> authenticate.authenticate(PROJECT, "ada@example.com", ""))
                .satisfies(f -> assertThat(f.reason()).isEqualTo("no password supplied"));
    }

    private String messageFor(String email, String password) {
        try {
            authenticate.authenticate(PROJECT, email, password);
            throw new AssertionError("expected authentication to fail for " + email);
        } catch (AuthenticationFailed failed) {
            return failed.getMessage();
        }
    }
}
