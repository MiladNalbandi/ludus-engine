// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.SchemaVersionStamper;
import io.ludus.domain.content.ContentBody;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * The only code in the engine that changes a document's bytes, and it does so exactly once.
 *
 * <p>{@code schema_version} is optional on the wire and load-bearing once stored: a client uses it
 * to decide whether it understands a document at all, and the rule it relies on — ignore anything
 * newer than you were built against, play the rest — only works if every stored document declares
 * one. So a document that arrives without it gets the current generation.
 *
 * <p>Everything else about the storage design exists to keep bytes byte-identical, so this is the
 * documented exception. Two things keep it honest: it returns the body untouched when a version is
 * already present, so the common path changes nothing; and it happens on the way in, before the
 * hash anyone will ever see is computed, so no ETag moves as a result.
 *
 * <p>It is deliberately not a flag on the reader. One implementation, one call site, and a test
 * asserting that a document which already declares a version comes back identical.
 */
@Component
public class JacksonSchemaVersionStamper implements SchemaVersionStamper {

    static final String FIELD = "schema_version";

    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public ContentBody stampIfAbsent(ContentBody body, int currentVersion) {
        JsonNode document;
        try {
            document = mapper.readTree(body.json());
        } catch (JsonProcessingException notJson) {
            throw new ContentRejected(
                    List.of(
                            ContentViolation.atRoot(
                                    "not valid JSON: " + notJson.getOriginalMessage())));
        }

        if (!document.isObject()) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("a document must be a JSON object")));
        }
        if (document.hasNonNull(FIELD)) {
            // The common case, and the one that must not touch the bytes.
            return body;
        }

        ((ObjectNode) document).put(FIELD, currentVersion);
        try {
            return new ContentBody(mapper.writeValueAsString(document));
        } catch (JsonProcessingException impossible) {
            throw new IllegalStateException("could not re-serialise a document just parsed", impossible);
        }
    }
}
