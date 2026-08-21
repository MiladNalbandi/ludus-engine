// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.shared;

import java.util.regex.Pattern;

/**
 * A stable, human-authored identifier for a piece of content.
 *
 * <p>The pattern is deliberately narrow. These identifiers end up in URLs, in filenames when
 * content is exported, and in the JSON documents game clients cache by name, so anything that
 * needs escaping in one of those places is not allowed in the first place.
 */
public record Slug(String value) {

    /** Mirrors the {@code id} pattern in the wire schema. Both must be changed together. */
    private static final Pattern PATTERN = Pattern.compile("^[a-z0-9_]+$");

    public static final int MAX_LENGTH = 64;

    public Slug {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("slug must not be blank");
        }
        if (value.length() > MAX_LENGTH) {
            throw new IllegalArgumentException(
                    "slug must be at most " + MAX_LENGTH + " characters, was " + value.length());
        }
        if (!PATTERN.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "slug must match " + PATTERN.pattern() + ", was '" + value + "'");
        }
    }

    public static boolean isValid(String candidate) {
        return candidate != null
                && !candidate.isBlank()
                && candidate.length() <= MAX_LENGTH
                && PATTERN.matcher(candidate).matches();
    }

    @Override
    public String toString() {
        return value;
    }
}
