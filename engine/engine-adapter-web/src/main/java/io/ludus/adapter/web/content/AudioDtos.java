// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.domain.content.AudioClip;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;

final class AudioDtos {

    private AudioDtos() {}

    @Schema(name = "AudioClipSummary", description = "An audio clip's metadata. The bytes are fetched from the stream route.")
        record Summary(
            String id,
            String filename,
            String contentType,
            long sizeBytes,
            Instant createdAt) {

        static Summary of(AudioClip clip) {
            return new Summary(
                    clip.id().toString(),
                    clip.filename(),
                    clip.contentType(),
                    clip.sizeBytes(),
                    clip.createdAt());
        }
    }
}
