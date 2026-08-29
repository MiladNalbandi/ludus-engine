// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security;

import io.ludus.application.identity.port.out.PasswordHasher;
import io.ludus.domain.identity.PasswordHash;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * BCrypt, at the default work factor.
 *
 * <p>Chosen over anything faster because slow is the feature: the threat model for a password is
 * someone holding the database and guessing. Chosen over Argon2 only because BCrypt is in
 * spring-security-crypto with no further dependency, and the difference between the two matters
 * far less than the difference between either and a plain digest.
 */
@Component
public class BCryptPasswordHasher implements PasswordHasher {

    /**
     * A valid BCrypt hash of a value nobody knows, used to spend the time a real comparison would.
     * Generated once at construction rather than hard-coded, so this file contains no hash of
     * anything and a secret scanner has nothing to find.
     */
    private final String decoy;

    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    public BCryptPasswordHasher() {
        this.decoy = encoder.encode(java.util.UUID.randomUUID().toString());
    }

    @Override
    public PasswordHash hash(String rawPassword) {
        if (rawPassword == null || rawPassword.isEmpty()) {
            throw new IllegalArgumentException("cannot hash an empty password");
        }
        // BCrypt silently ignores everything past 72 bytes, so a 200-character passphrase is
        // really a 72-byte one. Refusing is better than quietly storing less than was typed.
        if (rawPassword.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 72) {
            throw new IllegalArgumentException(
                    "password must be at most 72 bytes; BCrypt ignores anything beyond that,"
                            + " which would silently store less than was typed");
        }
        return new PasswordHash(encoder.encode(rawPassword));
    }

    @Override
    public boolean matches(String rawPassword, PasswordHash hash) {
        if (rawPassword == null || hash == null) {
            return false;
        }
        return encoder.matches(rawPassword, hash.value());
    }

    @Override
    public boolean matchesNothing(String rawPassword) {
        encoder.matches(rawPassword == null ? "" : rawPassword, decoy);
        return false;
    }
}
