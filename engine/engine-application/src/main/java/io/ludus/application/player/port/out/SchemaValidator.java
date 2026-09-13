// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.application.content.ContentViolation;
import io.ludus.domain.content.ContentBody;
import java.util.List;

/**
 * Validates a document against a schema supplied at the same time.
 *
 * <p>Distinct from {@code DocumentValidator}, which validates against the <em>bundled</em> wave
 * schema and knows its URI. This one is handed both the document and the schema, because the schema
 * belongs to the project and arrives from the database.
 *
 * <p>That difference matters more than it looks. A project-supplied schema is untrusted input: it
 * can be malformed, it can be enormous, and it can contain constructs — a remote {@code $ref}, in
 * particular — that would have the engine fetch a URL of somebody else's choosing. An
 * implementation of this port is responsible for refusing all of that, and the port says so here so
 * that a second implementation cannot quietly not.
 */
public interface SchemaValidator {

    /**
     * @return every violation, or empty when the document satisfies the schema
     * @throws SchemaUnusable when the schema itself cannot be used
     */
    List<ContentViolation> validate(ContentBody schema, ContentBody document);

    /** Checks a schema is usable, so a bad one is refused when it is set rather than on first use. */
    void requireUsable(ContentBody schema);

    /** The schema is not a schema, or asks for something that will not be done. */
    class SchemaUnusable extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public SchemaUnusable(String message) {
            super(message);
        }

        public SchemaUnusable(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
