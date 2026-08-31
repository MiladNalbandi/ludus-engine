// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.application.content.ContentViolation;
import io.ludus.domain.content.ContentBody;
import java.util.List;

/**
 * Checks a document against the published schema.
 *
 * <p>A port because the application layer may not import a JSON Schema library — it may not import
 * a JSON library at all. What it needs is the answer, and the answer is a list of violations at
 * JSON Pointer paths, which is expressible without either.
 *
 * <p>An empty list means valid. There is no "warn" mode: an engine that persists content it knows
 * to be invalid is a bad default for something a game client will later be handed.
 */
public interface DocumentValidator {

    List<ContentViolation> validate(ContentBody body);

    /**
     * The identifier of the schema documents are checked against, stored alongside each one.
     *
     * <p>Recorded per document rather than assumed globally, because a second content type is
     * coming and the two will not share a schema.
     */
    String schemaUri();
}
