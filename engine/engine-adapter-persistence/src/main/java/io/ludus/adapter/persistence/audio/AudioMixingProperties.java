// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * How, and whether, this install mixes audio.
 *
 * <p>`none` is the default and is what the plain image ships with. FFmpeg is a large dependency
 * with its own vulnerability history, and the roadmap is explicit that a self-hoster must never
 * have to install it to get a working engine — so there are two images, and the feature is off
 * unless the one that has the tool is running with it switched on.
 */
@ConfigurationProperties(prefix = "ludus.audio.mixer")
public record AudioMixingProperties(
        Mode mode, String binary, Duration timeout, long maxOutputBytes, int maxTracks) {

    public enum Mode {
        /** Mixing is refused. The default. */
        NONE,
        /** Mixing runs FFmpeg, which must be on the image. */
        FFMPEG
    }

    public AudioMixingProperties {
        mode = mode == null ? Mode.NONE : mode;
        // An absolute path, not a name to be found on PATH. A name is resolved against an
        // environment the engine does not control, and "whatever ffmpeg means here" is not a thing
        // to hand a subprocess.
        binary = binary == null || binary.isBlank() ? "/usr/bin/ffmpeg" : binary;
        timeout = timeout == null ? Duration.ofSeconds(60) : timeout;
        maxOutputBytes = maxOutputBytes <= 0 ? 64L * 1024 * 1024 : maxOutputBytes;
        maxTracks = maxTracks <= 0 ? 8 : maxTracks;
    }
}
