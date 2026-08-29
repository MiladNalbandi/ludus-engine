// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

/**
 * A stored password, after hashing. Never the password itself.
 *
 * <p>The type exists so that a method taking a hash cannot be handed a plaintext password by a
 * caller who did not read the parameter name. Two {@code String}s make that mistake invisible,
 * and the failure is silent: everything works, and the database fills with plaintext.
 *
 * <p>{@link #toString()} does not return the hash. A hash in a log is not a catastrophe the way a
 * password is, but it is an offline cracking target, and it has no business being there.
 */
public record PasswordHash(String value) {

    public PasswordHash {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("password hash must not be blank");
        }
    }

    @Override
    public String toString() {
        return "PasswordHash[redacted]";
    }
}
