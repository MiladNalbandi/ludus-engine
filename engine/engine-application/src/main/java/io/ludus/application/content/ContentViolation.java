// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

/**
 * One thing wrong with a document, and exactly where.
 *
 * <p>The pointer is an RFC 6901 JSON Pointer — {@code /progression_config/order}, not
 * {@code progression_config.order} and not a sentence describing the location. An editor maps each
 * violation onto the field that produced it and highlights it; a prose location cannot be mapped,
 * so the error ends up in a toast at the top of the screen and the author goes hunting.
 *
 * <p>Rules the schema cannot express report at the same pointers as the schema's own errors, so a
 * caller never has to care which kind of check produced a given violation.
 */
public record ContentViolation(String pointer, String message) {

    public ContentViolation {
        if (pointer == null) {
            throw new IllegalArgumentException("a violation must say where it is");
        }
        if (!pointer.isEmpty() && !pointer.startsWith("/")) {
            throw new IllegalArgumentException(
                    "a JSON Pointer is empty or starts with '/', was: " + pointer);
        }
        if (message == null || message.isBlank()) {
            throw new IllegalArgumentException("a violation must say what is wrong");
        }
    }

    /** The document as a whole, rather than a field within it. */
    public static ContentViolation atRoot(String message) {
        return new ContentViolation("", message);
    }
}
