// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class IdentityValuesTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");

    @Test
    void roles_are_ordered_so_that_a_higher_one_includes_the_lower_ones() {
        assertThat(Role.ADMIN.includes(Role.EDITOR)).isTrue();
        assertThat(Role.ADMIN.includes(Role.VIEWER)).isTrue();
        assertThat(Role.EDITOR.includes(Role.VIEWER)).isTrue();
        assertThat(Role.EDITOR.includes(Role.ADMIN)).isFalse();
        assertThat(Role.VIEWER.includes(Role.EDITOR)).isFalse();
        assertThat(Role.VIEWER.includes(Role.VIEWER)).isTrue();
    }

    @Test
    void an_unknown_role_name_is_refused_rather_than_defaulted() {
        assertThat(Role.fromString(" admin ")).isEqualTo(Role.ADMIN);
        assertThatIllegalArgumentException().isThrownBy(() -> Role.fromString("superuser"));
        assertThatIllegalArgumentException().isThrownBy(() -> Role.fromString(""));
    }

    /**
     * A hash in a log is an offline cracking target that nobody chose to put there. Both secret
     * types refuse to print themselves, so an accidental interpolation cannot leak one.
     */
    @Test
    void stored_secrets_do_not_print_themselves() {
        assertThat(new PasswordHash("$2a$10$realbcrypthashgoeshere").toString())
                .doesNotContain("realbcrypthash");
        assertThat(new SecretDigest("deadbeef").toString()).doesNotContain("deadbeef");
        assertThat("" + new PasswordHash("x-secret-x")).doesNotContain("x-secret-x");
    }

    @Test
    void a_user_cannot_exist_without_a_project() {
        assertThatIllegalArgumentException()
                .isThrownBy(
                        () ->
                                new User(
                                        UserId.random(),
                                        null,
                                        new EmailAddress("ada@example.com"),
                                        new PasswordHash("h"),
                                        Role.VIEWER,
                                        true,
                                        NOW));
    }

    @Test
    void revoking_an_api_key_twice_keeps_the_first_time() {
        ApiKey key =
                ApiKey.create(
                        ProjectId.random(),
                        "android",
                        "ludus_ab",
                        new SecretDigest("d"),
                        Role.VIEWER,
                        NOW);

        ApiKey revoked = key.revokedAt(NOW.plusSeconds(10));
        ApiKey again = revoked.revokedAt(NOW.plusSeconds(99));

        assertThat(again.revokedAt()).isEqualTo(NOW.plusSeconds(10));
        assertThat(key.isRevoked()).as("the original value is unchanged").isFalse();
    }

    @Test
    void a_refresh_token_must_expire_after_it_was_issued() {
        assertThatIllegalArgumentException()
                .isThrownBy(
                        () ->
                                RefreshToken.issue(
                                        ProjectId.random(),
                                        UserId.random(),
                                        new SecretDigest("d"),
                                        NOW,
                                        NOW));
    }

    @Test
    void a_refresh_token_is_usable_until_it_expires_or_is_revoked() {
        RefreshToken token =
                RefreshToken.issue(
                        ProjectId.random(),
                        UserId.random(),
                        new SecretDigest("d"),
                        NOW,
                        NOW.plusSeconds(60));

        assertThat(token.isUsableAt(NOW.plusSeconds(59))).isTrue();
        assertThat(token.isUsableAt(NOW.plusSeconds(60))).isFalse();
        assertThat(token.revokedAt(NOW.plusSeconds(1)).isUsableAt(NOW.plusSeconds(2))).isFalse();
    }
}
