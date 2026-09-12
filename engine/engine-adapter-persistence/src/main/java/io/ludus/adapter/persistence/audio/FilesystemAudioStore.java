// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import io.ludus.application.content.port.out.AudioStore;
import io.ludus.domain.content.AudioClipId;
import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Optional;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Audio bytes on a filesystem, streamed in and out.
 *
 * <p>Nothing here ever holds a whole clip. {@link Files#copy} moves bytes through a small buffer,
 * and reads hand back an open stream for the caller to drain. The predecessor read whole files into
 * a 256 MB heap, and a handful of players starting a level together was enough to end the process;
 * {@code AudioStreamingIT} runs an upload and a download of a 12 MB clip under {@code -Xmx256m} so
 * that regression cannot come back quietly.
 *
 * <p>Files are named by id and nothing else. The uploaded filename is metadata and never reaches
 * this class, so there is no path for a client-chosen string to influence.
 */
@Component
@EnableConfigurationProperties(AudioStorageProperties.class)
public class FilesystemAudioStore implements AudioStore {

    private final Path directory;

    FilesystemAudioStore(AudioStorageProperties properties) {
        String configured = properties.getDirectory();
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException(
                    """
                    LUDUS_AUDIO_DIRECTORY is not set.

                    Audio bytes are written to a directory on disk rather than into the database. \
                    It has to be a volume that survives a container restart -- deploy/docker-compose.yml \
                    provides one. See docs/operations/configuration.md.""");
        }
        this.directory = Path.of(configured).toAbsolutePath().normalize();
    }

    /**
     * Fails the start rather than the first upload.
     *
     * <p>A directory that is missing or read-only is a deployment mistake, and the useful moment to
     * find out is while somebody is still watching the deploy — not hours later when an author
     * uploads something.
     */
    @PostConstruct
    void ensureWritable() {
        try {
            Files.createDirectories(directory);
        } catch (IOException cannotCreate) {
            throw new IllegalStateException(
                    "audio directory " + directory + " could not be created", cannotCreate);
        }
        if (!Files.isWritable(directory)) {
            throw new IllegalStateException("audio directory " + directory + " is not writable");
        }
    }

    @Override
    public long store(AudioClipId id, InputStream bytes) {
        Path target = pathFor(id);
        // Written beside the target and moved into place, so a failed or interrupted upload cannot
        // leave a half-written file that a later read would serve as if it were whole.
        Path partial = target.resolveSibling(target.getFileName() + ".partial");
        try {
            long written = Files.copy(bytes, partial, StandardCopyOption.REPLACE_EXISTING);
            Files.move(partial, target, StandardCopyOption.REPLACE_EXISTING);
            return written;
        } catch (IOException failed) {
            deleteQuietly(partial);
            throw new UncheckedIOException("could not store audio " + id, failed);
        }
    }

    @Override
    public Optional<InputStream> open(AudioClipId id) {
        Path source = pathFor(id);
        if (!Files.isRegularFile(source)) {
            return Optional.empty();
        }
        try {
            return Optional.of(Files.newInputStream(source));
        } catch (IOException unreadable) {
            throw new UncheckedIOException("could not read audio " + id, unreadable);
        }
    }

    @Override
    public boolean delete(AudioClipId id) {
        try {
            return Files.deleteIfExists(pathFor(id));
        } catch (IOException failed) {
            throw new UncheckedIOException("could not delete audio " + id, failed);
        }
    }

    private Path pathFor(AudioClipId id) {
        // A UUID's string form contains only hex and hyphens, so this cannot escape the directory.
        // Resolved and re-checked anyway, because "cannot" is a claim worth making the code state.
        Path resolved = directory.resolve(id.value().toString()).normalize();
        if (!resolved.startsWith(directory)) {
            throw new IllegalArgumentException("audio id resolved outside the store: " + id);
        }
        return resolved;
    }

    private void deleteQuietly(Path path) {
        try {
            Files.deleteIfExists(path);
        } catch (IOException ignored) {
            // Already failing; a leftover .partial is a smaller problem than losing the cause.
        }
    }
}
