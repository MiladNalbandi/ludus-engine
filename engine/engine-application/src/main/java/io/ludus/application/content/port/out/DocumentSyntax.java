// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.ContentBody;
import java.util.Optional;

/**
 * Is this text JSON at all?
 *
 * <p>Separate from {@link DocumentValidator}, which answers a different question — does this
 * document satisfy its schema — and cannot be asked about a document with no schema. Application
 * configuration has none by design.
 *
 * <p>It exists because the generated {@code jsonb} column refuses anything unparseable, and a
 * malformed body reaching the database surfaces as a constraint error rather than as a message
 * naming the line the author got wrong.
 */
public interface DocumentSyntax {

    /** The reason it will not parse, or empty when it parses. */
    Optional<String> syntaxErrorIn(ContentBody body);
}
