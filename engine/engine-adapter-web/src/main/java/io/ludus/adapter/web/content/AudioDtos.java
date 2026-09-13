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

    @Schema(name = "AudioMixRequest", description = "The clips to combine, and how loud each should be.")
    record MixRequest(String filename, java.util.List<MixTrack> tracks) {}

    @Schema(name = "AudioMixTrack", description = "One clip in a mix. Gain is in decibels; 0 leaves it alone.")
    record MixTrack(String clipId, Double gainDb) {

        /**
         * A malformed id becomes null rather than an exception.
         *
         * <p>It cannot name a clip that exists, so the use case reports it as a missing clip at the
         * index that carried it -- alongside any others -- instead of the request failing with a
         * 500 on the first bad character.
         */
        io.ludus.application.content.AudioLibrary.MixTrack toDomain() {
            io.ludus.domain.content.AudioClipId id;
            try {
                id = clipId == null ? null : io.ludus.domain.content.AudioClipId.of(clipId);
            } catch (IllegalArgumentException notAnId) {
                id = null;
            }
            return new io.ludus.application.content.AudioLibrary.MixTrack(
                    id, gainDb == null ? 0.0 : gainDb);
        }
    }
}
