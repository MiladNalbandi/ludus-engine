// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.ContentBody;
import java.util.Optional;

/**
 * Reads the few fields the engine indexes out of a document.
 *
 * <p>Reads, and never writes. The distinction is the whole reason this interface is so narrow: the
 * moment something parses a document and serialises the result back, the stored bytes change and
 * every ETag with them. Extracting a value cannot do that; there is one port that may write, and it
 * is {@link SchemaVersionStamper}.
 *
 * <p>The fields here are precisely the columns in the {@code wave} table, and the list is short on
 * purpose. Every addition is a column, a migration, and another way for the document and the index
 * to disagree.
 */
public interface DocumentReader {

    /**
     * @throws io.ludus.application.content.ContentRejected if the body is not JSON at all — there
     *     is nothing useful to say about a document that cannot be parsed, so it fails here rather
     *     than producing a hundred schema violations
     */
    IndexedFields read(ContentBody body);

    /** What the engine stores in columns beside the document. */
    record IndexedFields(String id, String name, int order, Optional<Integer> schemaVersion) {}
}
