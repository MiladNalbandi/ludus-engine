// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

/**
 * A content document, exactly as it was received.
 *
 * <p>A string, and deliberately not a parsed object. The engine stores what the client sent and
 * serves those same bytes back, because the ETag is a hash of them: parse and re-serialise
 * anywhere on that path and the bytes move for reasons that have nothing to do with the content —
 * key order, null handling, {@code 1.0} coming back as {@code 1}.
 *
 * <p>Nothing in the domain or the application layer can read inside this. That is not an oversight:
 * both are framework-free and a JSON parser is a framework. Reading a field out of a document is an
 * outbound port, which keeps the number of places that can accidentally re-serialise it to one.
 */
public record ContentBody(String json) {

    public ContentBody {
        if (json == null || json.isBlank()) {
            throw new IllegalArgumentException("content body must not be blank");
        }
    }

    public int length() {
        return json.length();
    }

    /** Truncated, because a document is far too big to be useful in a log line or a test failure. */
    @Override
    public String toString() {
        return "ContentBody[" + json.length() + " chars]";
    }
}
