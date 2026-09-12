// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;

/**
 * The settings a game client reads at launch.
 *
 * <p>Free-form, deliberately. Waves have a schema because the engine interprets them — it derives
 * an order, a name and a publication state from the document. Nothing here is interpreted by the
 * engine at all; it is carried from an editor to a client, and what the keys mean is a matter
 * between the game and whoever tunes it. Imposing a schema would mean a release of Ludus every time
 * a game wanted a new difficulty knob.
 *
 * <p>Stored verbatim, like a wave, and for the sharper version of the same reason: this document is
 * fetched by every client on every launch, so a hash that moves when nothing changed costs more
 * here than anywhere else.
 */
public record AppConfig(ProjectId projectId, ContentBody body, Instant updatedAt) {

    /**
     * What a project that has never been configured has.
     *
     * <p>An empty object rather than nothing, because "no overrides" is exactly what an empty
     * object says, and a client that has to handle an absent document as a separate case will
     * handle it wrongly in one of its platforms. This differs from the active level, where absence
     * is a real state a game must cope with — there is no content to play — while an unconfigured
     * game plays perfectly well on its built-in defaults.
     */
    public static final String EMPTY = "{}";

    public AppConfig {
        if (projectId == null) {
            throw new IllegalArgumentException("app config must belong to a project");
        }
        if (body == null) {
            throw new IllegalArgumentException("app config must have a body");
        }
        if (updatedAt == null) {
            throw new IllegalArgumentException("app config must carry its timestamp");
        }
    }

    public static AppConfig empty(ProjectId projectId, Instant now) {
        return new AppConfig(projectId, new ContentBody(EMPTY), now);
    }
}
