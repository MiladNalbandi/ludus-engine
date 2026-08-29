// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

/**
 * A stored machine-generated secret, after a deterministic digest.
 *
 * <p>Distinct from {@link PasswordHash}, and the distinction is the point.
 *
 * <p>A password is short, low-entropy and chosen by a human, so it is stored with an adaptive,
 * salted hash whose whole purpose is to be slow: the threat is someone with the database
 * guessing their way in. A refresh token or an API key is 256 random bits, so guessing is not a
 * threat, and there is nothing to gain by making each check slow.
 *
 * <p>The practical consequence is why this type exists at all. A salted hash is different every
 * time it is computed, so a presented value cannot be looked up by hashing it — you would have to
 * fetch every row and compare. A deterministic digest is one indexed equality match, which is
 * what makes these credentials checkable at the rate a game client presents them.
 */
public record SecretDigest(String value) {

    public SecretDigest {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("secret digest must not be blank");
        }
    }

    @Override
    public String toString() {
        return "SecretDigest[redacted]";
    }
}
