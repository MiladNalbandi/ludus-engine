// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.AppConfigRepository;
import io.ludus.application.content.port.out.DocumentSyntax;
import io.ludus.domain.content.AppConfig;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.util.List;

/**
 * Reading and replacing the settings a game client fetches at launch.
 *
 * <p>Replace, never patch. A merge endpoint has to decide what a null means, whether an absent key
 * removes or preserves, and how deep to go — three questions with no answer the engine can give,
 * since it does not know what any of the keys mean. An editor sends the whole document and the
 * whole document is what clients get.
 */
public class ApplicationConfig {

    private final AppConfigRepository configs;
    private final DocumentSyntax syntax;
    private final Clock clock;

    public ApplicationConfig(
            AppConfigRepository configs, DocumentSyntax syntax, Clock clock) {
        this.configs = configs;
        this.syntax = syntax;
        this.clock = clock;
    }

    /**
     * The project's configuration, or an empty document when it has never been set.
     *
     * <p>Never empty as an {@code Optional}. A client asking what its settings are always has an
     * answer, and "none configured" is spelled {@code {}} rather than by a missing response.
     */
    public AppConfig current(ProjectId projectId) {
        return configs.find(projectId)
                .orElseGet(() -> AppConfig.empty(projectId, clock.instant()));
    }

    public AppConfig replace(ProjectId projectId, ContentBody body) {
        if (body == null) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("a configuration document must not be empty")));
        }
        syntax.syntaxErrorIn(body)
                .ifPresent(
                        error -> {
                            throw new ContentRejected(List.of(ContentViolation.atRoot(error)));
                        });
        return configs.save(new AppConfig(projectId, body, clock.instant()));
    }
}
