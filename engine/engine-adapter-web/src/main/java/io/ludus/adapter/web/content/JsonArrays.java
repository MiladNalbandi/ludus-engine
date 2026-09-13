// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.domain.content.ContentBody;
import java.util.ArrayList;
import java.util.List;

/**
 * Splits a JSON array into the exact bytes of each element.
 *
 * <p>Finds boundaries; does not interpret. That distinction is the reason this exists rather than a
 * {@code List<JsonNode>} parameter: binding the request to mapped objects, or to a list of
 * {@code JsonNode}, means every document is parsed and re-serialised on its way through — and the
 * stored bytes would then be Jackson's rendering rather than the author's. Every ETag in the
 * catalogue is a hash of those bytes, so an import through a re-serialising path would invalidate
 * every client's cache for documents whose content had not changed.
 *
 * <p>So this walks the string tracking nesting depth and string state, and hands back substrings.
 * Whether each substring is valid JSON is not decided here — it is decided by the validator that
 * every single-document save already goes through, which is what keeps the bulk path from being a
 * second, laxer way in.
 */
final class JsonArrays {

    private JsonArrays() {}

    static List<ContentBody> split(String array) {
        if (array == null || array.isBlank()) {
            throw refuse("the request had no documents in it");
        }

        String trimmed = array.trim();
        if (trimmed.charAt(0) != '[' || trimmed.charAt(trimmed.length() - 1) != ']') {
            throw refuse("the body must be a JSON array of documents");
        }

        List<ContentBody> documents = new ArrayList<>();
        int depth = 0;
        int elementStart = -1;
        boolean inString = false;
        boolean escaped = false;
        // A comma promises another element. Without this, "[{...},]" ended the loop with nothing
        // pending and was accepted as a single document -- invalid JSON, silently tolerated.
        boolean expectingElement = false;

        // The outer brackets are excluded, so depth 0 here means "between elements".
        for (int i = 1; i < trimmed.length() - 1; i++) {
            char c = trimmed.charAt(i);

            if (inString) {
                // An escape consumes whatever follows it, which is what stops \" from being read
                // as the end of the string and \\ from escaping the quote after it.
                if (escaped) {
                    escaped = false;
                } else if (c == '\\') {
                    escaped = true;
                } else if (c == '"') {
                    inString = false;
                }
                continue;
            }

            if (c == '"') {
                inString = true;
                if (elementStart < 0) {
                    elementStart = i;
                    expectingElement = false;
                }
                continue;
            }
            if (c == '{' || c == '[') {
                if (depth == 0 && elementStart < 0) {
                    elementStart = i;
                    expectingElement = false;
                }
                depth++;
                continue;
            }
            if (c == '}' || c == ']') {
                depth--;
                continue;
            }
            if (c == ',' && depth == 0) {
                documents.add(element(trimmed, elementStart, i));
                elementStart = -1;
                expectingElement = true;
                continue;
            }
            if (depth == 0 && elementStart < 0 && !Character.isWhitespace(c)) {
                // A bare scalar. Not a document, but its boundary is found the same way so that
                // the violation names the element rather than the whole request.
                elementStart = i;
                expectingElement = false;
            }
        }

        if (depth != 0 || inString || expectingElement) {
            throw refuse("the body is not a well-formed JSON array");
        }
        if (elementStart >= 0) {
            documents.add(element(trimmed, elementStart, trimmed.length() - 1));
        }
        if (documents.isEmpty()) {
            throw refuse("send at least one document");
        }
        return documents;
    }

    private static ContentBody element(String source, int start, int end) {
        if (start < 0) {
            throw refuse("the body is not a well-formed JSON array");
        }
        String slice = source.substring(start, end).trim();
        if (slice.isEmpty()) {
            throw refuse("the body is not a well-formed JSON array");
        }
        return new ContentBody(slice);
    }

    private static ContentRejected refuse(String message) {
        return new ContentRejected(List.of(ContentViolation.atRoot(message)));
    }
}
