// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import org.junit.jupiter.api.Test;

/**
 * The `v1.0.0` promise, checked rather than stated.
 *
 * <p>{@code docs/api/openapi-v1.json} is the contract as frozen at `1.0.0`. This compares the
 * current document against it and fails on anything a client could break on. It is deliberately
 * <em>not</em> a diff: the snapshot test already fails on any change at all, which is the right
 * signal for a reviewer and the wrong one for a promise, because it cannot tell an added endpoint
 * from a deleted one and so gets regenerated without being read.
 *
 * <p>What counts as breaking, and why each one:
 *
 * <ul>
 *   <li><b>Removing a path or an operation.</b> Every client calling it stops working.
 *   <li><b>Removing a schema</b> that the frozen document referenced.
 *   <li><b>Removing a property from a schema.</b> A client reading it gets null.
 *   <li><b>Making an optional request property required.</b> Every client that omits it starts
 *       failing.
 *   <li><b>Removing a value from an enum.</b> A client that sends it starts failing.
 * </ul>
 *
 * <p>Adding paths, operations, optional properties and enum values is <b>not</b> breaking, and this
 * test stays quiet about all of it — which is what makes it worth reading when it does speak.
 *
 * <p>When it fires and the change is genuinely wanted, the answer is a major version and a new
 * frozen baseline, not an edit to this file.
 */
class FrozenContractTest {

    private static final Path FROZEN = Path.of("..", "..", "docs", "api", "openapi-v1.json");
    private static final Path CURRENT = Path.of("..", "..", "docs", "api", "openapi.json");

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private static JsonNode read(Path path) throws IOException {
        assertThat(path).exists();
        return MAPPER.readTree(Files.readString(path, StandardCharsets.UTF_8));
    }

    @Test
    void nothing_a_client_depends_on_has_been_taken_away() throws IOException {
        JsonNode frozen = read(FROZEN);
        JsonNode current = read(CURRENT);

        List<String> breakages = new ArrayList<>();
        checkPaths(frozen, current, breakages);
        checkSchemas(frozen, current, breakages);

        assertThat(breakages)
                .as(
                        """
                        The HTTP contract frozen at 1.0.0 has been broken.

                        Each line below is something a client depends on and can no longer rely on. \
                        Adding paths, operations, optional fields and enum values is fine and this \
                        check says nothing about them -- these are removals and tightenings.

                        If the change is genuinely wanted, it costs a major version: bump to 2.0.0 \
                        and replace docs/api/openapi-v1.json with the new baseline. Editing this \
                        test is not the fix.

                        %s
                        """,
                        String.join("\n", breakages))
                .isEmpty();
    }

    private void checkPaths(JsonNode frozen, JsonNode current, List<String> breakages) {
        JsonNode frozenPaths = frozen.path("paths");
        JsonNode currentPaths = current.path("paths");

        for (Iterator<Map.Entry<String, JsonNode>> paths = frozenPaths.fields(); paths.hasNext(); ) {
            Map.Entry<String, JsonNode> path = paths.next();
            JsonNode currentPath = currentPaths.path(path.getKey());

            if (currentPath.isMissingNode()) {
                breakages.add("removed path: " + path.getKey());
                continue;
            }
            for (Iterator<String> methods = path.getValue().fieldNames(); methods.hasNext(); ) {
                String method = methods.next();
                if (currentPath.path(method).isMissingNode()) {
                    breakages.add("removed operation: " + method.toUpperCase() + " " + path.getKey());
                }
            }
        }
    }

    private void checkSchemas(JsonNode frozen, JsonNode current, List<String> breakages) {
        JsonNode frozenSchemas = frozen.path("components").path("schemas");
        JsonNode currentSchemas = current.path("components").path("schemas");

        for (Iterator<Map.Entry<String, JsonNode>> schemas = frozenSchemas.fields(); schemas.hasNext(); ) {
            Map.Entry<String, JsonNode> schema = schemas.next();
            JsonNode currentSchema = currentSchemas.path(schema.getKey());

            if (currentSchema.isMissingNode()) {
                breakages.add("removed schema: " + schema.getKey());
                continue;
            }

            JsonNode frozenProperties = schema.getValue().path("properties");
            JsonNode currentProperties = currentSchema.path("properties");
            for (Iterator<String> names = frozenProperties.fieldNames(); names.hasNext(); ) {
                String property = names.next();
                if (currentProperties.path(property).isMissingNode()) {
                    breakages.add("removed property: " + schema.getKey() + "." + property);
                }
            }

            // Newly required fields break every client that omitted them.
            TreeSet<String> newlyRequired = required(currentSchema);
            newlyRequired.removeAll(required(schema.getValue()));
            for (String property : newlyRequired) {
                breakages.add("newly required: " + schema.getKey() + "." + property);
            }

            checkEnums(schema.getKey(), frozenProperties, currentProperties, breakages);
        }
    }

    private void checkEnums(
            String schemaName, JsonNode frozenProperties, JsonNode currentProperties, List<String> breakages) {

        for (Iterator<Map.Entry<String, JsonNode>> properties = frozenProperties.fields();
                properties.hasNext(); ) {
            Map.Entry<String, JsonNode> property = properties.next();
            JsonNode frozenEnum = property.getValue().path("enum");
            if (!frozenEnum.isArray()) {
                continue;
            }
            JsonNode currentEnum = currentProperties.path(property.getKey()).path("enum");
            TreeSet<String> present = new TreeSet<>();
            currentEnum.forEach(value -> present.add(value.asText()));

            for (JsonNode value : frozenEnum) {
                if (!present.contains(value.asText())) {
                    breakages.add(
                            "removed enum value: "
                                    + schemaName
                                    + "."
                                    + property.getKey()
                                    + " = "
                                    + value.asText());
                }
            }
        }
    }

    private TreeSet<String> required(JsonNode schema) {
        TreeSet<String> required = new TreeSet<>();
        schema.path("required").forEach(value -> required.add(value.asText()));
        return required;
    }
}
