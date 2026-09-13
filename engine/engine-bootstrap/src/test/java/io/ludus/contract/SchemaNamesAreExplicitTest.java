// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.contract;

import static org.assertj.core.api.Assertions.assertThat;

import io.swagger.v3.oas.annotations.media.Schema;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;

/**
 * Every response and request type in the API must name its own schema.
 *
 * <p>springdoc names a schema after the Java class's simple name when nothing tells it otherwise,
 * and when two classes share a simple name it keeps one of them. Four records here were called
 * {@code Summary} — waves, wave levels, audio clips and API keys — so the published contract
 * described all four endpoints with the wave fields. A generated client was correct for one of them
 * and wrong about the other three, and nothing failed: the document was valid, the endpoints worked,
 * and only the description was a lie.
 *
 * <p>The snapshot test would have shown the collision as a diff. It would not have said what the
 * diff meant, and "the wave-levels response now references Summary" reads like housekeeping. This
 * test is the one that names the problem.
 *
 * <p>It checks the classes rather than the document, because the document only shows the winner.
 */
class SchemaNamesAreExplicitTest {

    /** Nested records in these packages are the API's request and response types. */
    private static final String WEB_PACKAGE = "io.ludus.adapter.web";

    @Test
    void every_api_record_declares_an_explicit_schema_name() throws Exception {
        List<Class<?>> apiRecords = apiRecords();

        assertThat(apiRecords)
                .as("no API records were found at all, which means this test is checking nothing")
                .isNotEmpty();

        List<String> unnamed = new ArrayList<>();
        for (Class<?> record : apiRecords) {
            Schema schema = record.getAnnotation(Schema.class);
            if (schema == null || schema.name().isBlank()) {
                unnamed.add(record.getName());
            }
        }

        assertThat(unnamed)
                .as(
                        """
                        These records appear in the HTTP API without an explicit schema name, so \
                        springdoc will name them after their simple name -- and silently keep only \
                        one of any two that collide.

                        Add @Schema(name = "SomethingSpecific") to each:
                        %s
                        """,
                        String.join("\n", unnamed))
                .isEmpty();
    }

    @Test
    void no_two_api_records_share_a_schema_name() throws Exception {
        Map<String, List<String>> byName = new java.util.LinkedHashMap<>();
        for (Class<?> record : apiRecords()) {
            Schema schema = record.getAnnotation(Schema.class);
            String name = schema == null || schema.name().isBlank() ? record.getSimpleName() : schema.name();
            byName.computeIfAbsent(name, key -> new ArrayList<>()).add(record.getName());
        }

        List<String> collisions =
                byName.entrySet().stream()
                        .filter(entry -> entry.getValue().size() > 1)
                        .map(entry -> entry.getKey() + " <- " + entry.getValue())
                        .toList();

        assertThat(collisions)
                .as("two records claiming one schema name means one of them is not in the contract")
                .isEmpty();
    }

    /**
     * Records nested inside the web adapter's DTO holders and controllers.
     *
     * <p>Found by walking the compiled classes rather than by a hand-maintained list, because a
     * list is the thing that goes stale the first time somebody adds a controller — which is
     * exactly when this check matters.
     */
    private static List<Class<?>> apiRecords() throws Exception {
        Path root =
                Paths.get(
                        Class.forName("io.ludus.adapter.web.content.WaveDtos")
                                .getProtectionDomain()
                                .getCodeSource()
                                .getLocation()
                                .toURI());

        List<Class<?>> found = new ArrayList<>();
        if (Files.isDirectory(root)) {
            collectFrom(root, found);
        } else {
            collectFromJar(root, found);
        }
        return found;
    }

    private static void collectFrom(Path root, List<Class<?>> found) throws IOException {
        try (Stream<Path> files = Files.walk(root)) {
            files.filter(path -> path.toString().endsWith(".class"))
                    .map(path -> className(root.relativize(path).toString()))
                    .forEach(name -> addIfApiRecord(name, found));
        }
    }

    private static void collectFromJar(Path jar, List<Class<?>> found) throws IOException {
        try (var archive = new java.util.jar.JarFile(jar.toFile())) {
            archive.stream()
                    .map(java.util.zip.ZipEntry::getName)
                    .filter(name -> name.endsWith(".class"))
                    .map(SchemaNamesAreExplicitTest::className)
                    .forEach(name -> addIfApiRecord(name, found));
        }
    }

    private static String className(String path) {
        return path.replace(java.io.File.separatorChar, '.').replace('/', '.').replaceAll("\\.class$", "");
    }

    private static void addIfApiRecord(String name, List<Class<?>> found) {
        if (!name.startsWith(WEB_PACKAGE) || !name.contains("$")) {
            return;
        }
        try {
            Class<?> candidate = Class.forName(name);
            if (candidate.isRecord()) {
                found.add(candidate);
            }
        } catch (ClassNotFoundException | NoClassDefFoundError notLoadable) {
            // Not something the API can reference either.
        }
    }
}
