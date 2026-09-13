// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.contract;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.Test;

/**
 * Every setting the engine reads is documented, and everything documented is read.
 *
 * <p>An acceptance criterion of `v1.0.0`, and the direction people forget is the second one.
 * Undocumented settings are the familiar problem: an operator finds them by reading source code, or
 * does not find them at all. Documented settings that no longer exist are worse, because somebody
 * sets one, watches nothing happen, and has no way to tell whether the engine ignored it or they
 * spelled it wrong. Both are the same failure this codebase keeps coming back to — a document
 * asserting something untrue.
 *
 * <p>Checked by comparing the text of {@code application.yml} with the text of the configuration
 * guide, rather than by starting the application. A running context knows the properties it bound;
 * it does not know which environment variables were meant to feed them, which is the thing an
 * operator actually types.
 */
class ConfigurationIsDocumentedTest {

    /** Relative to this module, which is two levels below the repository root. */
    private static final Path APPLICATION_YML = Path.of("src", "main", "resources", "application.yml");

    private static final Path GUIDE = Path.of("..", "..", "docs", "operations", "configuration.md");

    private static final Path ENV_EXAMPLE = Path.of("..", "..", "deploy", ".env.example");

    /** `${LUDUS_SOMETHING:default}` or `${LUDUS_SOMETHING}` in the YAML. */
    private static final Pattern CONFIGURED = Pattern.compile("\\$\\{(LUDUS_[A-Z0-9_]+)");

    /** `` `LUDUS_SOMETHING` `` in the guide — the form every table row uses. */
    private static final Pattern DOCUMENTED = Pattern.compile("`(LUDUS_[A-Z0-9_]+)`");

    /** `LUDUS_SOMETHING=` at the start of a line in the sample env file. */
    private static final Pattern SAMPLED = Pattern.compile("(?m)^(LUDUS_[A-Z0-9_]+)=");

    private static Set<String> matches(Path file, Pattern pattern) throws IOException {
        assertThat(file).as("%s must exist for this check to mean anything", file).exists();
        Matcher matcher = pattern.matcher(Files.readString(file, StandardCharsets.UTF_8));
        Set<String> found = new TreeSet<>();
        while (matcher.find()) {
            found.add(matcher.group(1));
        }
        return found;
    }

    @Test
    void every_setting_the_engine_reads_is_in_the_configuration_guide() throws IOException {
        Set<String> configured = matches(APPLICATION_YML, CONFIGURED);
        Set<String> documented = matches(GUIDE, DOCUMENTED);

        assertThat(configured).as("nothing was found in application.yml; this check is broken").isNotEmpty();

        Set<String> undocumented = new TreeSet<>(configured);
        undocumented.removeAll(documented);

        assertThat(undocumented)
                .as(
                        """
                        These settings are read by application.yml and are not in \
                        docs/operations/configuration.md. An operator finds an undocumented \
                        setting by reading source code, or does not find it at all.

                        Add a row for each: %s
                        """,
                        undocumented)
                .isEmpty();
    }

    @Test
    void every_setting_in_the_guide_is_one_the_engine_actually_reads() throws IOException {
        Set<String> configured = matches(APPLICATION_YML, CONFIGURED);
        Set<String> documented = matches(GUIDE, DOCUMENTED);

        // Set by compose rather than read by the engine: the editor is a separate service, and its
        // settings belong in the same guide because an operator does not care which container
        // reads them. Named here so the exception is explicit rather than a loosened check.
        Set<String> readElsewhere =
                Set.of("LUDUS_EDITOR_PORT", "LUDUS_EDITOR_HTTPS", "LUDUS_ENGINE_URL");

        Set<String> stale = new TreeSet<>(documented);
        stale.removeAll(configured);
        stale.removeAll(readElsewhere);

        assertThat(stale)
                .as(
                        """
                        These settings are documented and the engine no longer reads them. Somebody \
                        will set one, watch nothing happen, and have no way to tell whether it was \
                        ignored or misspelled -- which is worse than not documenting it.

                        Remove or correct each: %s
                        """,
                        stale)
                .isEmpty();
    }

    @Test
    void the_sample_env_file_only_names_settings_that_exist() throws IOException {
        Set<String> sampled = matches(ENV_EXAMPLE, SAMPLED);
        Set<String> configured = matches(APPLICATION_YML, CONFIGURED);
        Set<String> editorSettings = Set.of("LUDUS_EDITOR_PORT", "LUDUS_EDITOR_HTTPS");

        assertThat(sampled).isNotEmpty();

        Set<String> unknown = new TreeSet<>(sampled);
        unknown.removeAll(configured);
        unknown.removeAll(editorSettings);

        assertThat(unknown)
                .as(
                        "deploy/.env.example is the file people copy; a setting in it that nothing"
                                + " reads is one somebody will rely on: %s",
                        unknown)
                .isEmpty();
    }
}
