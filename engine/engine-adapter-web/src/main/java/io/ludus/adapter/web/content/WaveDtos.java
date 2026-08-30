// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.domain.content.Wave;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

final class WaveDtos {

    private WaveDtos() {}

    /**
     * A wave without its document.
     *
     * <p>The list endpoint returns these rather than embedding every document, because an editor
     * listing forty waves wants forty names and no megabytes. The document is fetched on its own.
     */
    @Schema(description = "A wave's indexed fields. The document itself is fetched separately.")
    record Summary(
            String id,
            String name,
            int order,
            int schemaVersion,
            boolean published,
            Instant createdAt,
            Instant updatedAt) {

        static Summary of(Wave wave) {
            return new Summary(
                    wave.id().value(),
                    wave.name(),
                    wave.order(),
                    wave.schemaVersion(),
                    wave.published(),
                    wave.createdAt(),
                    wave.updatedAt());
        }
    }
}
