// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.port.out.SchemaValidator;
import io.ludus.domain.content.ContentBody;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * A schema an editor wrote is untrusted input, and these are the refusals that make it safe to use.
 *
 * <p>The one that matters most is the remote {@code $ref}. A schema containing
 * {@code {"$ref": "https://attacker.example/s.json"}} would have the engine fetch a URL of the
 * author's choosing from inside the deployment's network — server-side request forgery, reachable
 * by anyone who can edit a schema, and the sort of thing that does not announce itself.
 */
class NetworkntSchemaValidatorTest {

    private final NetworkntSchemaValidator validator = new NetworkntSchemaValidator();

    private static ContentBody body(String json) {
        return new ContentBody(json);
    }

    // ------------------------------------------------------------------ the refusals

    @ParameterizedTest
    @ValueSource(
            strings = {
                "{\"$ref\": \"https://attacker.example/schema.json\"}",
                "{\"$ref\":\"http://169.254.169.254/latest/meta-data/\"}",
                "{\"properties\":{\"a\":{\"$ref\": \"file:///etc/passwd\"}}}",
                "{\"properties\":{\"a\":{\"$ref\":\"other.json\"}}}",
                "{\"$REF\": \"https://attacker.example/s.json\"}",
                "{\"items\":{\"$ref\" : \"//attacker.example/s.json\"}}"
            })
    void a_schema_with_a_non_local_ref_is_refused(String schema) {
        assertThatThrownBy(() -> validator.requireUsable(body(schema)))
                .as("an engine that fetched this would be a request-forgery hole")
                .isInstanceOf(SchemaValidator.SchemaUnusable.class)
                .hasMessageContaining("local $ref");
    }

    @Test
    void a_local_ref_is_allowed_because_it_fetches_nothing() {
        ContentBody schema =
                body(
                        """
                        {
                          "$defs": {"positive": {"type": "integer", "minimum": 1}},
                          "type": "object",
                          "properties": {"damage": {"$ref": "#/$defs/positive"}}
                        }
                        """);

        validator.requireUsable(schema);

        assertThat(validator.validate(schema, body("{\"damage\": 5}"))).isEmpty();
        assertThat(validator.validate(schema, body("{\"damage\": 0}"))).isNotEmpty();
    }

    @Test
    void a_schema_larger_than_the_cap_is_refused() {
        String enormous =
                "{\"type\":\"object\",\"description\":\""
                        + "x".repeat(NetworkntSchemaValidator.MAX_SCHEMA_BYTES)
                        + "\"}";

        assertThatThrownBy(() -> validator.requireUsable(body(enormous)))
                .as("it is validated against every item on every save, and it persists in a table")
                .isInstanceOf(SchemaValidator.SchemaUnusable.class)
                .hasMessageContaining("at most");
    }

    @Test
    void a_schema_that_is_not_json_is_refused_when_it_is_set() {
        assertThatThrownBy(() -> validator.requireUsable(body("{\"type\": }")))
                .isInstanceOf(SchemaValidator.SchemaUnusable.class)
                .hasMessageContaining("valid JSON");
    }

    @Test
    void a_schema_that_is_json_but_not_a_schema_is_refused() {
        // A JSON array is not a schema. Refused when set, not on the first item somebody creates.
        assertThatThrownBy(() -> validator.requireUsable(body("[1, 2, 3]")))
                .isInstanceOf(SchemaValidator.SchemaUnusable.class);
    }

    // ------------------------------------------------------------------ validation

    @Test
    void a_document_satisfying_the_schema_has_no_violations() {
        ContentBody schema =
                body(
                        """
                        {"type":"object","required":["damage"],
                         "properties":{"damage":{"type":"integer","minimum":1}},
                         "additionalProperties":false}
                        """);

        assertThat(validator.validate(schema, body("{\"damage\": 12}"))).isEmpty();
    }

    @Test
    void violations_are_reported_at_json_pointer_paths() {
        ContentBody schema =
                body(
                        """
                        {"type":"object","properties":{"stats":{"type":"object",
                         "properties":{"damage":{"type":"integer"}}}}}
                        """);

        assertThat(validator.validate(schema, body("{\"stats\":{\"damage\":\"lots\"}}")))
                .as("an editor maps each violation onto the field that caused it")
                .extracting(ContentViolation::pointer)
                .containsExactly("/stats/damage");
    }

    @Test
    void every_violation_is_returned_rather_than_the_first() {
        ContentBody schema =
                body(
                        """
                        {"type":"object","required":["a","b","c"],
                         "properties":{"a":{"type":"integer"},"b":{"type":"integer"},
                                       "c":{"type":"integer"}}}
                        """);

        assertThat(validator.validate(schema, body("{}")))
                .as("correcting a document one round trip per problem is the slowest possible way")
                .hasSize(3);
    }

    @Test
    void a_document_that_is_not_json_is_one_violation_at_the_root() {
        ContentBody schema = body("{\"type\":\"object\"}");

        assertThat(validator.validate(schema, body("{not json")))
                .singleElement()
                .extracting(ContentViolation::pointer)
                .isEqualTo("");
    }

    @Test
    void the_same_document_produces_the_same_order_of_violations() {
        ContentBody schema =
                body(
                        """
                        {"type":"object","required":["z","a","m"],
                         "properties":{"z":{"type":"integer"},"a":{"type":"integer"},
                                       "m":{"type":"integer"}}}
                        """);

        assertThat(validator.validate(schema, body("{}")))
                .as("an editor highlighting fields should not see them reorder between saves")
                .isEqualTo(validator.validate(schema, body("{}")));
    }

    @Test
    void an_empty_schema_accepts_anything() {
        // The default for a project that has not declared one: a game that has not decided what its
        // items look like should not be stopped from creating one.
        assertThat(validator.validate(body("{}"), body("{\"anything\": true}"))).isEmpty();
    }
}
