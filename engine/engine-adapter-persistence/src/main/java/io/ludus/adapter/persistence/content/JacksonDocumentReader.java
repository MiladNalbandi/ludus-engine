// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.DocumentReader;
import io.ludus.domain.content.ContentBody;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * Pulls the indexed fields out of a document, and writes nothing back.
 *
 * <p>Every method here reads from a parsed tree and returns a Java value. Nothing serialises. That
 * is the whole discipline: the moment a document is parsed and written back out, the bytes change —
 * key order, whitespace, {@code 1.0} becoming {@code 1} — and every ETag changes with them. The one
 * place allowed to do that is {@link JacksonSchemaVersionStamper}, and it is separate so that this
 * distinction is visible in the imports rather than remembered.
 */
@Component
public class JacksonDocumentReader implements DocumentReader {

    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public IndexedFields read(ContentBody body) {
        JsonNode document = parse(body);

        return new IndexedFields(
                requiredText(document, "id"),
                requiredText(document, "name"),
                requiredOrder(document),
                Optional.ofNullable(document.get("schema_version"))
                        .filter(JsonNode::isInt)
                        .map(JsonNode::asInt));
    }

    private JsonNode parse(ContentBody body) {
        try {
            JsonNode document = mapper.readTree(body.json());
            if (!document.isObject()) {
                throw new ContentRejected(
                        List.of(ContentViolation.atRoot("a document must be a JSON object")));
            }
            return document;
        } catch (JsonProcessingException notJson) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("not valid JSON: " + notJson.getOriginalMessage())));
        }
    }

    private String requiredText(JsonNode document, String field) {
        JsonNode value = document.get(field);
        if (value == null || !value.isTextual() || value.asText().isBlank()) {
            // Schema validation runs before this and should have caught it. Reaching here means
            // the schema and the fields the engine indexes have drifted apart, which is worth
            // saying rather than failing with a NullPointerException three frames later.
            throw new ContentRejected(
                    List.of(new ContentViolation("/" + field, "is required and must be text")));
        }
        return value.asText();
    }

    private int requiredOrder(JsonNode document) {
        JsonNode order =
                Optional.ofNullable(document.get("progression_config"))
                        .map(config -> config.get("order"))
                        .orElse(null);

        if (order == null || !order.isInt()) {
            throw new ContentRejected(
                    List.of(
                            new ContentViolation(
                                    io.ludus.domain.content.WaveOrderPolicy.ORDER_POINTER,
                                    "is required and must be an integer")));
        }
        return order.asInt();
    }
}
