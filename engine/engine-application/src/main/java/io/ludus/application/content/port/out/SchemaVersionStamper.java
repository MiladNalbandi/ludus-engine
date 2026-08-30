// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.ContentBody;

/**
 * The one path in the engine that is allowed to change a document's bytes.
 *
 * <p>{@code schema_version} is optional on the wire and authoritative once stored, because a client
 * relies on it to decide whether it understands a document at all. A document that arrives without
 * one gets the current generation stamped in.
 *
 * <p>Everything else about the storage design exists to keep bytes identical, so this is the
 * documented exception and it is deliberately its own port rather than a flag on
 * {@link DocumentReader}. A single implementation, a single call site, and a test asserting that a
 * document which already carries a version comes back byte-identical.
 *
 * <p>The edit is surgical — one field added to the parsed tree — not a reformat. It still moves the
 * bytes, which is why it happens once, on the way in, before the hash anyone will ever see is taken.
 */
public interface SchemaVersionStamper {

    /**
     * @return the body unchanged if it already declares a version, otherwise a copy carrying the
     *     current one
     */
    ContentBody stampIfAbsent(ContentBody body, int currentVersion);
}
