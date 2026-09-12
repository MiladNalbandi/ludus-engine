// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import io.ludus.application.content.port.out.AudioMixer;
import java.util.List;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * The mixer most installs have: one that says no.
 *
 * <p>A bean rather than a null or an empty {@code Optional}, so every caller has a mixer and the
 * question "is mixing configured" is asked of it rather than of the container. The refusal names
 * the two things an operator has to change, because "mixing is not available" with no further
 * detail sends someone reading source code.
 */
@Component
@ConditionalOnProperty(name = "ludus.audio.mixer.mode", havingValue = "none", matchIfMissing = true)
public class RefusingAudioMixer implements AudioMixer {

    @Override
    public boolean available() {
        return false;
    }

    @Override
    public Mixed mix(List<Source> sources) {
        throw new MixFailed(
                """
                This engine cannot mix audio.

                Mixing needs FFmpeg, which the standard image deliberately does not carry: it is a \
                large dependency with its own vulnerability history, and a self-hosted install \
                should not have to acquire it to get a working engine.

                To enable it, run the ffmpeg image and switch the mode on:

                    image: ghcr.io/miladnalbandi/ludus-engine-ffmpeg:<tag>
                    LUDUS_AUDIO_MIXER_MODE=ffmpeg

                Clips can still be uploaded and served; only mixing several into one is refused.""");
    }
}
