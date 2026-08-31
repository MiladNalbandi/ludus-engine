// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import java.util.Arrays;
import java.util.List;

/**
 * Reading an {@code If-None-Match} header, tolerantly.
 *
 * <p>This is unglamorous and it is the single easiest place in the caching protocol to silently
 * lose. Getting it wrong does not fail: the server simply never returns {@code 304}, every client
 * on the affected platform re-downloads everything on every launch, and nothing anywhere reports a
 * problem. It is the same shape of failure as unstable stored bytes, arriving from a different
 * direction.
 *
 * <p>So it accepts what real clients and proxies actually send, rather than what the specification
 * says they should:
 *
 * <ul>
 *   <li>weak validators — {@code W/"abc"} — which caches add on their own
 *   <li>quoted and unquoted forms, because plenty of HTTP stacks drop the quotes
 *   <li>comma-separated lists, which is how a client offers several cached copies
 *   <li>{@code *}, meaning "any representation you have"
 * </ul>
 *
 * <p>Comparison is deliberately weak: {@code W/"x"} matches {@code "x"}. Strong comparison exists
 * for byte-range requests, and nothing here serves ranges. Treating them as different would mean
 * refusing to honour a cache entry that is, in fact, current.
 *
 * <p>Pure JDK, in the domain, so the whole thing is a table test rather than something that needs a
 * servlet to exercise.
 */
public final class EntityTags {

    /** Matches any representation the server holds. */
    public static final String ANY = "*";

    private EntityTags() {}

    /**
     * Does the client already hold this version?
     *
     * @param ifNoneMatch the raw header, or null when absent
     * @param currentTag the tag of what would be served, unquoted
     * @return true if the response should be {@code 304}
     */
    public static boolean matches(String ifNoneMatch, String currentTag) {
        if (ifNoneMatch == null || ifNoneMatch.isBlank() || currentTag == null) {
            return false;
        }
        String current = normalise(currentTag);
        if (current.isEmpty()) {
            return false;
        }
        return candidates(ifNoneMatch).stream()
                .anyMatch(candidate -> ANY.equals(candidate) || candidate.equals(current));
    }

    /** Splits a header into its individual validators, each normalised. */
    private static List<String> candidates(String header) {
        return Arrays.stream(header.split(","))
                .map(EntityTags::normalise)
                .filter(value -> !value.isEmpty())
                .toList();
    }

    /**
     * Strips whitespace, an optional weak marker, and optional surrounding quotes — in that order,
     * because {@code W/"abc"} has the marker outside the quotes.
     */
    private static String normalise(String value) {
        String trimmed = value.trim();
        if (trimmed.startsWith("W/") || trimmed.startsWith("w/")) {
            trimmed = trimmed.substring(2).trim();
        }
        if (trimmed.length() >= 2 && trimmed.startsWith("\"") && trimmed.endsWith("\"")) {
            trimmed = trimmed.substring(1, trimmed.length() - 1);
        }
        return trimmed;
    }

    /**
     * Wraps a tag for the {@code ETag} response header.
     *
     * <p>Quoted, because that is what the specification requires and what a proxy will expect to
     * see even though this parser tolerates its absence on the way in. Be strict in what you send.
     */
    public static String toHeader(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("cannot build an ETag header from an empty tag");
        }
        return "\"" + tag + "\"";
    }
}
