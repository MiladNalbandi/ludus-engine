// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import io.ludus.adapter.persistence.blob.FilesystemBlobs;
import io.ludus.application.content.port.out.AudioStore;
import io.ludus.domain.content.AudioClipId;
import jakarta.annotation.PostConstruct;
import java.io.InputStream;
import java.util.Optional;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Audio bytes on a filesystem, streamed in and out.
 *
 * <p>Nothing here ever holds a whole clip: the bytes move through a small buffer on the way in, and
 * reads hand back an open stream for the caller to drain. The predecessor read whole files into a
 * 256 MB heap, and a handful of players starting a level together was enough to end the process;
 * {@code AudioStreamingIT} pushes a clip larger than the whole heap through both directions so that
 * regression cannot come back quietly.
 *
 * <p>The filesystem work itself is {@link FilesystemBlobs}, shared with sprites. It was extracted
 * rather than copied when the second caller appeared: the atomic write, the startup check and the
 * refusal to let a client-supplied name reach a path were all learned once, and should not have to
 * be learned again per asset type.
 *
 * <p>Files are named by id and nothing else. The uploaded filename is metadata and never reaches
 * this class.
 */
@Component
@EnableConfigurationProperties(AudioStorageProperties.class)
public class FilesystemAudioStore implements AudioStore {

    private final FilesystemBlobs blobs;

    FilesystemAudioStore(AudioStorageProperties properties) {
        this.blobs =
                new FilesystemBlobs(properties.getDirectory(), "audio", "LUDUS_AUDIO_DIRECTORY");
    }

    @PostConstruct
    void ensureWritable() {
        blobs.ensureWritable();
    }

    @Override
    public long store(AudioClipId id, InputStream bytes) {
        return blobs.store(id.value(), bytes);
    }

    @Override
    public Optional<InputStream> open(AudioClipId id) {
        return blobs.open(id.value());
    }

    @Override
    public boolean delete(AudioClipId id) {
        return blobs.delete(id.value());
    }
}
