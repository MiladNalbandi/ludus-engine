// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.stream.Collectors;

/**
 * The one function behind every "has this changed?" answer the engine gives.
 *
 * <p>A client learns that content changed two ways: it polls {@code /app/status} for a content
 * hash, and it revalidates individual responses with {@code If-None-Match} against an {@code
 * ETag}. Those are different mechanisms and it is tempting to implement them separately.
 *
 * <p>Doing so produces a bug that is very hard to see. The poll says "something changed", the
 * client refetches, and an HTTP cache validating against the other signal hands back {@code 304} —
 * or the reverse, the poll says nothing changed while a cache holds stale bytes. Both signals are
 * therefore computed here, by construction, so they cannot disagree.
 *
 * <p>Pure JDK on purpose: this lives in the domain, which bans every framework transitively, and it
 * is exactly the kind of rule that should be testable without one.
 */
public final class ContentHashes {

    public static final String PREFIX = "sha256:";

    private ContentHashes() {}

    /**
     * Hashes one document's stored bytes. This is the {@code ETag} of a raw content response, and
     * the reason the storage column is {@code text} rather than {@code jsonb}.
     */
    public static String ofDocument(ContentBody body) {
        if (body == null) {
            throw new IllegalArgumentException("cannot hash an absent document");
        }
        return digest(body.json());
    }

    /**
     * Hashes a catalogue: every entry's id and last-modified time, sorted by id.
     *
     * <p>Sorted because the hash must not depend on what order the database happened to return
     * rows in. Ids and timestamps rather than the documents themselves because this is called on
     * every poll and must stay cheap — a change to any document moves its {@code updatedAt}, so
     * the two are equivalent for the purpose of detecting change.
     *
     * <p>Used for both the {@code /app/status} content hash and the {@code ETag} of a list
     * response. Same input, same function, same answer.
     */
    public static String ofCatalogue(List<Entry> entries) {
        if (entries == null) {
            throw new IllegalArgumentException("cannot hash an absent catalogue");
        }
        String canonical =
                entries.stream()
                        .sorted(Comparator.comparing(Entry::id))
                        .map(entry -> entry.id() + ":" + entry.updatedAt().toString())
                        .collect(Collectors.joining("\n"));
        return digest(canonical);
    }

    private static String digest(String value) {
        try {
            MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
            return PREFIX
                    + HexFormat.of()
                            .formatHex(sha256.digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is not available", impossible);
        }
    }

    /** One catalogue member: what it is called, and when it last changed. */
    public record Entry(String id, Instant updatedAt) {

        public Entry {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("catalogue entry needs an id");
            }
            if (updatedAt == null) {
                throw new IllegalArgumentException("catalogue entry needs an updatedAt");
            }
        }
    }
}
