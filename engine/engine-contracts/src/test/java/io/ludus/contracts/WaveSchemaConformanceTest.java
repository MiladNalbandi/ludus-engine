// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.contracts;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.PathType;
import com.networknt.schema.SchemaValidatorsConfig;
import com.networknt.schema.SpecVersion;
import com.networknt.schema.ValidationMessage;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

/**
 * Every sample document is validated against the schema that ships in this jar.
 *
 * <p>Samples are the only executable documentation of the wire format, so a sample that has
 * drifted from the contract is worse than no sample: it teaches the wrong shape and is copied.
 * The editor runs the same samples through a JavaScript validator, which is what keeps the two
 * implementations honest about the same file.
 */
class WaveSchemaConformanceTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /**
     * JSON Pointer output is not the library default and has changed between versions. The
     * editor maps each error onto the field that produced it, so a change here silently breaks
     * error reporting rather than failing anything. Pin it.
     */
    private static final SchemaValidatorsConfig CONFIG =
            SchemaValidatorsConfig.builder().pathType(PathType.JSON_POINTER).build();

    private static JsonSchema waveSchema() throws IOException {
        try (InputStream in = WaveSchemaConformanceTest.class.getResourceAsStream("/schemas/wave/v1.json")) {
            assertThat(in)
                    .withFailMessage("/schemas/wave/v1.json is not on the classpath — the "
                            + "build-time copy from contracts/schemas did not run")
                    .isNotNull();
            return JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012)
                    .getSchema(in, CONFIG);
        }
    }

    static Stream<Path> sampleWaves() throws IOException {
        Path dir = Path.of("..", "..", "samples", "waves");
        assertThat(dir).as("sample directory").exists();
        try (Stream<Path> files = Files.list(dir)) {
            List<Path> samples = files.filter(p -> p.toString().endsWith(".json")).sorted().toList();
            assertThat(samples).as("sample waves").isNotEmpty();
            return samples.stream();
        }
    }

    @ParameterizedTest(name = "{0} conforms to the wave schema")
    @MethodSource("sampleWaves")
    void sample_conforms_to_the_published_schema(Path sample) throws IOException {
        JsonNode document = MAPPER.readTree(sample.toFile());

        Set<ValidationMessage> errors = waveSchema().validate(document);

        assertThat(errors)
                .withFailMessage(() -> sample.getFileName() + " does not conform:\n"
                        + errors.stream()
                                .map(e -> "  " + e.getInstanceLocation() + ": " + e.getMessage())
                                .sorted()
                                .reduce("", (a, b) -> a + b + "\n"))
                .isEmpty();
    }

    @Test
    void schema_compiles_and_reports_errors_as_json_pointers() throws IOException {
        JsonNode invalid = MAPPER.readTree("""
                {"id": "Not A Slug", "name": "x", "version": "1.0",
                 "spawn_rules": [], "constraints": {}, "progression_config": {}}
                """);

        Set<ValidationMessage> errors = waveSchema().validate(invalid);

        assertThat(errors).isNotEmpty();
        assertThat(errors)
                .extracting(e -> e.getInstanceLocation().toString())
                .allSatisfy(location -> assertThat(location).matches("^(/.*)?$"))
                .contains("/id");
    }
}
