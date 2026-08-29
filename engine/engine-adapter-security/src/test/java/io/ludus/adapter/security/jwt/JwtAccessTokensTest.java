// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.jwt;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalStateException;

import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.PasswordHash;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class JwtAccessTokensTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");

    private static final Clock CLOCK = Clock.fixed(NOW, ZoneOffset.UTC);

    private final JwtAccessTokens tokens =
            new JwtAccessTokens(properties("a-secret-of-quite-sufficient-length-for-hs256"), CLOCK);

    private final User ada =
            User.create(
                    ProjectId.random(),
                    new EmailAddress("ada@example.com"),
                    new PasswordHash("irrelevant"),
                    Role.EDITOR,
                    NOW);

    private static JwtProperties properties(String secret) {
        JwtProperties properties = new JwtProperties();
        properties.setSecret(secret);
        return properties;
    }

    @Test
    void a_token_it_issued_verifies_back_to_the_same_user_project_and_role() {
        String token = tokens.issue(ada, NOW, NOW.plus(Duration.ofMinutes(15)));

        assertThat(tokens.verify(token))
                .hasValueSatisfying(
                        verified -> {
                            assertThat(verified.userId()).isEqualTo(ada.id());
                            assertThat(verified.projectId()).isEqualTo(ada.projectId());
                            assertThat(verified.role()).isEqualTo(Role.EDITOR);
                        });
    }

    /** The whole point of a signature: a token signed with another key is not accepted. */
    @Test
    void a_token_signed_with_a_different_secret_is_rejected() {
        JwtAccessTokens attacker =
                new JwtAccessTokens(
                        properties("a-different-secret-also-long-enough-for-hs256"), CLOCK);

        assertThat(tokens.verify(attacker.issue(ada, NOW, NOW.plus(Duration.ofMinutes(15)))))
                .isEmpty();
    }

    /**
     * Expiry is judged against the injected clock, not the wall clock. The first version of this
     * class read the system time inside jjwt, and this test passed or failed depending on how far
     * the fixed instant in the test happened to be from today.
     */
    @Test
    void an_expired_token_is_rejected() {
        String expired = tokens.issue(ada, NOW.minusSeconds(3600), NOW.minusSeconds(1800));

        assertThat(tokens.verify(expired)).isEmpty();
    }

    @Test
    void a_token_is_valid_right_up_to_its_expiry() {
        String token = tokens.issue(ada, NOW, NOW.plusSeconds(60));

        assertThat(tokens.verify(token)).isPresent();

        JwtAccessTokens later =
                new JwtAccessTokens(
                        properties("a-secret-of-quite-sufficient-length-for-hs256"),
                        Clock.fixed(NOW.plusSeconds(61), ZoneOffset.UTC));
        assertThat(later.verify(token)).isEmpty();
    }

    @Test
    void rubbish_is_rejected_rather_than_throwing() {
        assertThat(tokens.verify("")).isEmpty();
        assertThat(tokens.verify("not.a.jwt")).isEmpty();
        assertThat(tokens.verify("a")).isEmpty();
    }

    /**
     * No default secret, ever. A signing secret published in a public repository is a working
     * forgery tool for every install that kept it.
     */
    @Test
    void the_engine_refuses_to_start_without_a_signing_secret() {
        assertThatIllegalStateException()
                .isThrownBy(() -> properties(null).validate())
                .withMessageContaining("LUDUS_JWT_SECRET is not set");

        assertThatIllegalStateException()
                .isThrownBy(() -> properties("   ").validate())
                .withMessageContaining("LUDUS_JWT_SECRET is not set");
    }

    @Test
    void a_secret_too_short_for_hs256_is_refused_with_a_way_to_make_one() {
        assertThatIllegalStateException()
                .isThrownBy(() -> properties("too-short").validate())
                .withMessageContaining("openssl rand");
    }

    @Test
    void a_refresh_lifetime_that_does_not_outlive_the_access_lifetime_is_refused() {
        JwtProperties properties = properties("a-secret-of-quite-sufficient-length-for-hs256");
        properties.setAccessTokenTtl(Duration.ofHours(2));
        properties.setRefreshTokenTtl(Duration.ofHours(1));

        assertThatIllegalStateException()
                .isThrownBy(properties::validate)
                .withMessageContaining("refreshing a token gains nothing");
    }

    @Test
    void the_secret_is_not_in_the_string_form_that_diagnostics_log() {
        assertThat(properties("a-secret-of-quite-sufficient-length-for-hs256").toString())
                .doesNotContain("a-secret-of-quite-sufficient-length")
                .contains("redacted");
    }
}
