// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import java.util.Locale;

/**
 * How a person is identified when they sign in.
 *
 * <p>Deliberately not a full RFC 5322 validator. The only questions worth answering here are
 * whether this could plausibly be routed to a human and whether two spellings of the same
 * address can end up as two accounts. Anything stricter rejects addresses that work, and the
 * real check is whether mail to it arrives.
 *
 * <p>Stored lower-cased, because {@code Ada@example.com} and {@code ada@example.com} are the same
 * mailbox everywhere it matters, and a unique constraint that disagrees is how one person ends
 * up with two accounts and no idea which one their password is on.
 */
public record EmailAddress(String value) {

    public static final int MAX_LENGTH = 254;

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("email address must not be blank");
        }
        value = value.trim().toLowerCase(Locale.ROOT);
        if (value.length() > MAX_LENGTH) {
            throw new IllegalArgumentException(
                    "email address must be at most " + MAX_LENGTH + " characters");
        }
        int at = value.indexOf('@');
        if (at <= 0 || at != value.lastIndexOf('@') || at == value.length() - 1) {
            throw new IllegalArgumentException(
                    "email address must contain exactly one '@', with something either side");
        }
        if (value.indexOf('.', at) < 0) {
            throw new IllegalArgumentException("email address must have a dot in its domain");
        }
        if (value.chars().anyMatch(Character::isWhitespace)) {
            throw new IllegalArgumentException("email address must not contain whitespace");
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
