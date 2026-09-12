// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.port.out.AppConfigRepository;
import io.ludus.application.content.port.out.DocumentSyntax;
import io.ludus.domain.content.AppConfig;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ApplicationConfigTest {

    private static final Instant NOW = Instant.parse("2026-09-12T11:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final ProjectId THEIRS = ProjectId.random();

    private final Configs configs = new Configs();
    private final Syntax syntax = new Syntax();
    private final ApplicationConfig config =
            new ApplicationConfig(configs, syntax, Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void a_project_that_has_never_been_configured_gets_an_empty_object() {
        assertThat(config.current(MINE).body().json())
                .as("'no overrides' is spelled {}, not by an absent response a client must special-case")
                .isEqualTo("{}");
    }

    @Test
    void the_stored_bytes_are_the_submitted_bytes() {
        String awkward = "{\"a\":1.0,   \"z\":true,\n \"b\":\"x\"}";

        config.replace(MINE, new ContentBody(awkward));

        assertThat(config.current(MINE).body().json())
                .as("whitespace, key order and 1.0-versus-1 must survive, or the ETag moves for nothing")
                .isEqualTo(awkward);
    }

    @Test
    void replacing_replaces_rather_than_merges() {
        config.replace(MINE, new ContentBody("{\"a\":1,\"b\":2}"));
        config.replace(MINE, new ContentBody("{\"a\":9}"));

        assertThat(config.current(MINE).body().json())
                .as("the engine does not know what any key means, so it cannot merge two documents")
                .isEqualTo("{\"a\":9}");
    }

    @Test
    void malformed_json_is_refused_with_the_parser_message_rather_than_reaching_the_database() {
        syntax.error = "unexpected '}' at line 1, column 8";

        assertThatThrownBy(() -> config.replace(MINE, new ContentBody("{\"a\":1,}")))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .singleElement()
                                        .satisfies(
                                                violation -> {
                                                    assertThat(violation.pointer()).isEmpty();
                                                    assertThat(violation.message())
                                                            .contains("line 1");
                                                }));

        assertThat(configs.saved).as("nothing unparseable is stored").isEmpty();
    }

    @Test
    void a_missing_document_is_refused() {
        // A blank one cannot get this far: ContentBody refuses it in its constructor, and the web
        // edge turns that into a 422 rather than letting it become a 500. This covers the caller
        // that passes nothing at all.
        assertThatThrownBy(() -> config.replace(MINE, null)).isInstanceOf(ContentRejected.class);
    }

    @Test
    void one_project_does_not_see_another_projects_configuration() {
        config.replace(MINE, new ContentBody("{\"secret\":true}"));

        assertThat(config.current(THEIRS).body().json()).isEqualTo("{}");
    }

    private static final class Configs implements AppConfigRepository {
        private final Map<ProjectId, AppConfig> saved = new HashMap<>();

        @Override
        public Optional<AppConfig> find(ProjectId projectId) {
            return Optional.ofNullable(saved.get(projectId));
        }

        @Override
        public AppConfig save(AppConfig config) {
            saved.put(config.projectId(), config);
            return config;
        }
    }

    /** Says what the test told it to, so the rejection path is exercised without a parser. */
    private static final class Syntax implements DocumentSyntax {
        String error;

        @Override
        public Optional<String> syntaxErrorIn(ContentBody body) {
            return Optional.ofNullable(error);
        }
    }
}
