// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import io.ludus.domain.identity.PasswordHash;
import org.junit.jupiter.api.Test;

/** The real hashing and digesting, as opposed to the stand-ins the use-case tests run against. */
class CredentialHandlingTest {

    private final BCryptPasswordHasher passwords = new BCryptPasswordHasher();
    private final Sha256SecretDigester digester = new Sha256SecretDigester();
    private final SecureRandomSecretGenerator secrets = new SecureRandomSecretGenerator();

    @Test
    void a_password_matches_its_own_hash_and_nothing_else() {
        PasswordHash hash = passwords.hash("correct-horse-battery-staple");

        assertThat(passwords.matches("correct-horse-battery-staple", hash)).isTrue();
        assertThat(passwords.matches("Correct-horse-battery-staple", hash)).isFalse();
        assertThat(passwords.matches("", hash)).isFalse();
        assertThat(passwords.matches(null, hash)).isFalse();
    }

    /** Salted, so the stored value differs every time even for the same password. */
    @Test
    void hashing_the_same_password_twice_gives_two_different_hashes() {
        assertThat(passwords.hash("same").value()).isNotEqualTo(passwords.hash("same").value());
    }

    @Test
    void the_stored_hash_does_not_contain_the_password() {
        assertThat(passwords.hash("swordfish").value()).doesNotContain("swordfish");
    }

    /**
     * BCrypt ignores everything past 72 bytes. Accepting a longer passphrase would silently store
     * a truncated one, so the user believes they have a stronger password than they do.
     */
    @Test
    void a_password_too_long_for_bcrypt_is_refused_rather_than_silently_truncated() {
        assertThatIllegalArgumentException()
                .isThrownBy(() -> passwords.hash("x".repeat(73)))
                .withMessageContaining("72");

        assertThat(passwords.hash("x".repeat(72))).isNotNull();
    }

    @Test
    void checking_against_nothing_always_fails_and_never_throws() {
        assertThat(passwords.matchesNothing("anything")).isFalse();
        assertThat(passwords.matchesNothing(null)).isFalse();
    }

    @Test
    void a_digest_is_deterministic_which_is_what_makes_a_lookup_possible() {
        assertThat(digester.digest("ludus_abc")).isEqualTo(digester.digest("ludus_abc"));
        assertThat(digester.digest("ludus_abc")).isNotEqualTo(digester.digest("ludus_abd"));
    }

    @Test
    void a_digest_is_hex_sha256_and_does_not_contain_its_input() {
        String digest = digester.digest("ludus_secret").value();

        assertThat(digest).hasSize(64).matches("[0-9a-f]{64}").doesNotContain("ludus_secret");
    }

    @Test
    void generated_secrets_are_long_url_safe_and_not_repeated() {
        String first = secrets.generate();

        assertThat(first).hasSizeGreaterThanOrEqualTo(43).matches("[A-Za-z0-9_-]+");
        assertThat(first).isNotEqualTo(secrets.generate());
    }
}
