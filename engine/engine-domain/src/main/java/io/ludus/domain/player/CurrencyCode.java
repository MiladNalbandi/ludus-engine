// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import java.util.regex.Pattern;

/**
 * The name of a currency, in the project's own vocabulary.
 *
 * <p>{@code coins}, {@code gems}, {@code energy} — whatever the game has. Not an enum, because an
 * enum means a release of Ludus every time a game invents one, and the engine never needs to know
 * what any of them mean: it adds and subtracts them and refuses to go below zero.
 *
 * <p>The same shape as {@link io.ludus.domain.shared.Slug} and validated the same way, so a
 * currency name is safe in a URL and in a JSON key without escaping.
 */
public record CurrencyCode(String value) {

    public static final int MAX_LENGTH = 40;
    private static final Pattern FORMAT = Pattern.compile("^[a-z0-9_]+$");

    public CurrencyCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("a currency code must not be blank");
        }
        if (value.length() > MAX_LENGTH) {
            throw new IllegalArgumentException(
                    "a currency code must be at most " + MAX_LENGTH + " characters");
        }
        if (!FORMAT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "a currency code must match ^[a-z0-9_]+$, was '" + value + "'");
        }
    }

    public static boolean isValid(String candidate) {
        return candidate != null
                && !candidate.isBlank()
                && candidate.length() <= MAX_LENGTH
                && FORMAT.matcher(candidate).matches();
    }

    @Override
    public String toString() {
        return value;
    }
}
