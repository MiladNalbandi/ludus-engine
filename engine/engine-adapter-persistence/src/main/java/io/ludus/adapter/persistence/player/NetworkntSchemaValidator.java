// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.InputFormat;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.PathType;
import com.networknt.schema.SchemaValidatorsConfig;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.port.out.SchemaValidator;
import io.ludus.domain.content.ContentBody;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

/**
 * Validates item attributes against a schema the project supplied.
 *
 * <p><b>A project-supplied schema is untrusted input, and that is the whole difficulty here.</b>
 * The wave schema ships in the jar and is as trustworthy as the build; this one arrives from a
 * database row that an editor wrote, so it can be malformed, enormous, or ask the engine to do
 * something on somebody else's behalf.
 *
 * <p>Three refusals, in order of how much they matter:
 *
 * <ul>
 *   <li><b>No remote {@code $ref}.</b> A schema containing {@code {"$ref":
 *       "https://attacker.example/s.json"}} would have the engine fetch a URL of the author's
 *       choosing, from inside the deployment's network — server-side request forgery, reachable by
 *       anyone who can edit a schema. Refused by inspecting the schema text before the library ever
 *       sees it, because refusing it afterwards means trusting the library's resolution order.
 *   <li><b>A size cap.</b> A schema is validated against every item on every save, and a
 *       pathological one is a denial of service that persists in a table.
 *   <li><b>It must parse as a schema at all</b>, checked when it is set rather than on the first
 *       item somebody tries to create.
 * </ul>
 */
@Component
public class NetworkntSchemaValidator implements SchemaValidator {

    /**
     * Generous for a real item schema and far below what it takes to be a problem. A project whose
     * item attributes need more than this has a modelling question rather than a limit question.
     */
    static final int MAX_SCHEMA_BYTES = 64 * 1024;

    /**
     * Any {@code $ref} whose target is not a local JSON pointer.
     *
     * <p>Matched on the text, deliberately, and before the library parses it. {@code "$ref": "#/..."}
     * is local and fine; anything else — an absolute URL, a relative file, a {@code urn:} — is
     * refused. Checking the parsed tree instead would mean walking every nested schema construct
     * and being confident the walk covers the ones a future draft adds.
     */
    private static final Pattern NON_LOCAL_REF =
            Pattern.compile("\"\\$ref\"\\s*:\\s*\"(?!#)", Pattern.CASE_INSENSITIVE);

    /** JSON Pointer output, pinned for the same reason as the wave validator. */
    private static final SchemaValidatorsConfig CONFIG =
            SchemaValidatorsConfig.builder().pathType(PathType.JSON_POINTER).build();

    private final ObjectMapper mapper = new ObjectMapper();

    @Override
    public void requireUsable(ContentBody schema) {
        compile(schema);
    }

    @Override
    public List<ContentViolation> validate(ContentBody schema, ContentBody document) {
        JsonSchema compiled = compile(schema);

        Set<ValidationMessage> errors;
        try {
            errors = compiled.validate(document.json(), InputFormat.JSON);
        } catch (RuntimeException notJson) {
            return List.of(ContentViolation.atRoot("not valid JSON: " + notJson.getMessage()));
        }

        return errors.stream()
                // Sorted by pointer so two identical documents produce identical responses; an
                // editor highlighting fields should not see them reorder between saves.
                .sorted(Comparator.comparing(ValidationMessage::getInstanceLocation, Comparator.comparing(Object::toString)))
                .map(
                        error ->
                                new ContentViolation(
                                        error.getInstanceLocation().toString(), error.getMessage()))
                .toList();
    }

    private JsonSchema compile(ContentBody schema) {
        String text = schema.json();

        if (text.length() > MAX_SCHEMA_BYTES) {
            throw new SchemaUnusable(
                    "an item schema must be at most "
                            + MAX_SCHEMA_BYTES
                            + " characters; this one is "
                            + text.length());
        }
        if (NON_LOCAL_REF.matcher(text).find()) {
            throw new SchemaUnusable(
                    "an item schema may only use local $ref targets, beginning '#'. A remote"
                            + " reference would have the engine fetch a URL chosen by whoever wrote"
                            + " the schema, from inside this deployment's network.");
        }

        com.fasterxml.jackson.databind.JsonNode parsed;
        try {
            // Parsed first, so "not JSON" is reported as that rather than as whatever the schema
            // factory says about an unparseable input.
            parsed = mapper.readTree(text);
        } catch (com.fasterxml.jackson.core.JsonProcessingException malformed) {
            throw new SchemaUnusable(
                    "an item schema must be valid JSON: " + malformed.getOriginalMessage());
        }

        // A JSON Schema is an object, or one of the two boolean schemas. An array is neither, and
        // the library accepts one without complaint -- it compiles to a schema that validates
        // nothing, so every item would pass and the project would believe it had validation.
        // Checked here because a lenient library is not a reason to be lenient.
        if (!parsed.isObject() && !parsed.isBoolean()) {
            throw new SchemaUnusable(
                    "an item schema must be a JSON object, or true/false; this is a "
                            + parsed.getNodeType().name().toLowerCase(java.util.Locale.ROOT));
        }

        try {
            return JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)
                    .getSchema(text, CONFIG);
        } catch (RuntimeException notASchema) {
            throw new SchemaUnusable(
                    "that is valid JSON but not a usable JSON Schema: " + notASchema.getMessage(),
                    notASchema);
        }
    }
}
