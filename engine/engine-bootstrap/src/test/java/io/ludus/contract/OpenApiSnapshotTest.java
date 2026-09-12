// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.contract;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

/**
 * The HTTP contract, committed to the repository and diffed on every build.
 *
 * <p>An OpenAPI document generated at runtime describes whatever the code currently does, which
 * makes it useless as a contract: it agrees with the implementation by construction, including the
 * day the implementation changes by accident. Committing it turns "the API changed" from something
 * nobody notices into a line in a diff that a reviewer has to look at and approve.
 *
 * <p>That matters more as `v1.0.0` approaches, because that release promises a frozen contract and
 * semantic versioning. A promise about a contract nobody is tracking is not a promise.
 *
 * <p>When this fails, read the diff first. If the change was intended, regenerate:
 *
 * <pre>{@code ./mvnw -pl engine/engine-bootstrap test -Dtest=OpenApiSnapshotTest -Dludus.openapi.write=true}</pre>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class OpenApiSnapshotTest {

    /** Relative to this module, which is two levels below the repository root. */
    private static final Path SNAPSHOT = Path.of("..", "..", "docs", "api", "openapi.json");

    private static final String WRITE_PROPERTY = "ludus.openapi.write";

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;

    OpenApiSnapshotTest(@Autowired TestRestTemplate rest) {
        this.rest = rest;
    }

    @Test
    void the_published_contract_has_not_changed_without_review() throws IOException {
        String current = canonical(rest.getForObject("http://localhost:" + port + "/api-docs", String.class));

        if (Boolean.getBoolean(WRITE_PROPERTY)) {
            Files.createDirectories(SNAPSHOT.getParent());
            Files.writeString(SNAPSHOT, current, StandardCharsets.UTF_8);
            return;
        }

        assertThat(SNAPSHOT)
                .withFailMessage(
                        "%s does not exist. Generate it with:%n  ./mvnw -pl engine/engine-bootstrap"
                                + " test -Dtest=OpenApiSnapshotTest -D%s=true",
                        SNAPSHOT, WRITE_PROPERTY)
                .exists();

        assertThat(current)
                .withFailMessage(
                        """
                        The HTTP contract changed.

                        That is not automatically wrong -- but it is public, and %s promises to \
                        freeze it. Read the diff against %s. If the change was intended, \
                        regenerate the snapshot and let the reviewer see it:

                          ./mvnw -pl engine/engine-bootstrap test -Dtest=OpenApiSnapshotTest -D%s=true
                        """,
                        "v1.0.0", SNAPSHOT, WRITE_PROPERTY)
                .isEqualTo(Files.readString(SNAPSHOT, StandardCharsets.UTF_8));
    }

    /**
     * Pretty-printed with keys sorted, and the version replaced.
     *
     * <p>Sorted because springdoc builds the document from a reflective scan and the order is not
     * guaranteed to be stable between runs. A snapshot that reorders itself would fail for reasons
     * nobody can act on, and a check that cries wolf gets regenerated without being read — which is
     * the same as not having one.
     *
     * <p>Two fields are removed or replaced because they describe the running instance rather than
     * the API: the version, which moves with every release, and the server URL, which under a
     * random-port test is different on every single run. The first draft of this kept both, and
     * the snapshot failed immediately against itself — which is the useful kind of early failure,
     * because a check that cannot agree with its own output is one people learn to regenerate
     * without reading.
     */
    private String canonical(String json) throws IOException {
        ObjectMapper mapper =
                new ObjectMapper()
                        .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS)
                        .enable(SerializationFeature.INDENT_OUTPUT);

        JsonNode document = mapper.readTree(json);

        if (document instanceof ObjectNode root) {
            // The server URL carries whatever port the app bound to, which under a random-port
            // test is different on every run. It describes where this instance happens to be
            // listening, not what it serves, so it is not part of the contract.
            root.remove("servers");
        }
        if (document.get("info") instanceof ObjectNode info) {
            info.put("version", "${project.version}");
        }
        return mapper.writeValueAsString(document) + "\n";
    }
}
