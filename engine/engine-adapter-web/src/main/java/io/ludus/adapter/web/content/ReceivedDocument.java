// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.domain.content.ContentBody;
import java.util.List;

/**
 * A request body, turned into a document or into an answer the caller can act on.
 *
 * <p>{@link ContentBody} refuses a blank document in its constructor, which is right — nothing
 * downstream should have to wonder. But an empty request body is an ordinary client mistake, and
 * an {@code IllegalArgumentException} escaping a controller is a {@code 500}: the engine reporting
 * its own failure for something the caller did. This is the edge, so this is where that becomes a
 * {@code 422}.
 *
 * <p><b>The controllers that use this declare {@code @RequestBody(required = false)}, and must.</b>
 * With the default, Spring refuses an empty body itself, before any controller code runs — and that
 * refusal goes out through the container's error dispatch, which re-enters the security filter
 * chain with no authentication in it. The caller gets a {@code 401} for a request that was
 * perfectly well authenticated. It is the same mechanism that once turned a {@code 403} into a
 * {@code 401} here, and it is just as hard to read from the outside: the status names the wrong
 * problem entirely.
 */
final class ReceivedDocument {

    private ReceivedDocument() {}

    static ContentBody of(String body) {
        if (body == null || body.isBlank()) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("the request had no document in it")));
        }
        return new ContentBody(body);
    }
}
