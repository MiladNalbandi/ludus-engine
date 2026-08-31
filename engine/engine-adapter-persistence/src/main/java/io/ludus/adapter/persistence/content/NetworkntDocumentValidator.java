// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.PathType;
import com.networknt.schema.SchemaValidatorsConfig;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.DocumentValidator;
import io.ludus.domain.content.ContentBody;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.InputStream;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Component;

/**
 * Validates a document against the wave schema shipped in the jar.
 *
 * <p>The schema is loaded once, at startup, and a failure to load it fails the start. The
 * alternative is that a schema which cannot be parsed is discovered by the first author who tries
 * to save something, hours after a deploy that reported success.
 */
@Component
public class NetworkntDocumentValidator implements DocumentValidator {

    /**
     * The classpath location of the schema, put there by the {@code copy-wire-schemas} execution
     * in {@code engine-contracts}. It is the same file the editor consumes from npm and the same
     * file the samples are checked against — there is no second copy to drift.
     */
    private static final String SCHEMA_RESOURCE = "/schemas/wave/v1.json";

    private static final String SCHEMA_URI = "https://ludus.dev/schemas/wave/v1.json";

    /**
     * JSON Pointer output is not the library default and has changed between versions. An editor
     * maps each violation onto the field that produced it, so if this drifts the error reporting
     * stops working without anything failing. Pinned here for the same reason it is pinned in
     * {@code WaveSchemaConformanceTest}.
     */
    private static final SchemaValidatorsConfig CONFIG =
            SchemaValidatorsConfig.builder().pathType(PathType.JSON_POINTER).build();

    private JsonSchema schema;

    @PostConstruct
    void loadSchema() {
        try (InputStream in = getClass().getResourceAsStream(SCHEMA_RESOURCE)) {
            if (in == null) {
                throw new IllegalStateException(
                        SCHEMA_RESOURCE
                                + " is not on the classpath. The build-time copy from"
                                + " contracts/schemas did not run.");
            }
            this.schema =
                    JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)
                            .getSchema(in, CONFIG);
        } catch (IOException unreadable) {
            throw new IllegalStateException("could not read " + SCHEMA_RESOURCE, unreadable);
        }
    }

    @Override
    public List<ContentViolation> validate(ContentBody body) {
        Set<ValidationMessage> errors;
        try {
            errors = schema.validate(body.json(), com.networknt.schema.InputFormat.JSON);
        } catch (RuntimeException notJson) {
            // Not parseable at all. One violation at the root beats a hundred derived from a
            // document the parser never understood.
            return List.of(ContentViolation.atRoot("not valid JSON: " + notJson.getMessage()));
        }

        return errors.stream()
                .map(
                        error ->
                                new ContentViolation(
                                        error.getInstanceLocation().toString(), error.getMessage()))
                // Sorted so the same document always produces the same order. An editor showing
                // errors in a different order on each save looks broken even when it is not.
                .sorted(
                        Comparator.comparing(ContentViolation::pointer)
                                .thenComparing(ContentViolation::message))
                .toList();
    }

    @Override
    public String schemaUri() {
        return SCHEMA_URI;
    }
}
