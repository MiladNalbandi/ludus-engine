// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.blob;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Optional;
import java.util.UUID;

/**
 * Uploaded bytes on a filesystem, addressed by UUID.
 *
 * <p>Extracted from {@code FilesystemAudioStore} when sprites needed the same thing, rather than
 * copied. The rules here are all ones that were learned once and should not have to be learned
 * again per asset type: write to a {@code .partial} and move it into place atomically, check the
 * directory at startup rather than on the first upload, and never let a client-supplied name reach
 * a path.
 *
 * <p>Not a Spring bean. It is constructed by each store with its own directory, so audio and
 * sprites cannot end up sharing one by accident — and the error messages can name the setting the
 * operator actually has to change.
 *
 * <p>{@code v1.1.0} turns content and entity types into data, at which point the asset types become
 * data too and this grows a namespace instead of a caller per kind. Until there is a second reason
 * to generalise, two callers is not one.
 */
public final class FilesystemBlobs {

    private final Path directory;
    private final String what;
    private final String setting;

    /**
     * @param what what is stored here, for error messages — "audio" or "sprites"
     * @param setting the environment variable an operator would change
     */
    public FilesystemBlobs(String configured, String what, String setting) {
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException(
                    ("""
                     %s is not set.

                     %s bytes are written to a directory on disk rather than into the database. It \
                     has to be a volume that survives a container restart -- deploy/docker-compose.yml \
                     provides one. See docs/operations/configuration.md.""")
                            .formatted(setting, what));
        }
        this.directory = Path.of(configured).toAbsolutePath().normalize();
        this.what = what;
        this.setting = setting;
    }

    /**
     * Fails the start rather than the first upload.
     *
     * <p>A directory that is missing or read-only is a deployment mistake, and the useful moment to
     * find out is while somebody is still watching the deploy — not hours later when an author
     * uploads something.
     */
    public void ensureWritable() {
        try {
            Files.createDirectories(directory);
        } catch (IOException cannotCreate) {
            throw new IllegalStateException(
                    what + " directory " + directory + " could not be created", cannotCreate);
        }
        if (!Files.isWritable(directory)) {
            throw new IllegalStateException(
                    ("""
                     The %s directory %s exists but is not writable by this process (uid %s).

                     Under Docker this usually means the volume was created before the directory \
                     existed in the image: an empty named volume inherits the mount point's owner, \
                     and a path Docker has to create itself is owned by root. Either rebuild the \
                     image (the Dockerfile creates it owned by the runtime user) or chown the \
                     existing volume. The setting is %s. See docs/operations/configuration.md.""")
                            .formatted(
                                    what,
                                    directory,
                                    System.getProperty("user.name", "unknown"),
                                    setting));
        }
    }

    /** Streams the bytes in. Nothing here ever holds a whole file. */
    public long store(UUID id, InputStream bytes) {
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
            throw new UncheckedIOException("could not store " + what + " " + id, failed);
        }
    }

    /** Hands back an open stream for the caller to drain and close. */
    public Optional<InputStream> open(UUID id) {
        Path source = pathFor(id);
        if (!Files.isRegularFile(source)) {
            return Optional.empty();
        }
        try {
            return Optional.of(Files.newInputStream(source));
        } catch (IOException unreadable) {
            throw new UncheckedIOException("could not read " + what + " " + id, unreadable);
        }
    }

    public boolean delete(UUID id) {
        try {
            return Files.deleteIfExists(pathFor(id));
        } catch (IOException failed) {
            throw new UncheckedIOException("could not delete " + what + " " + id, failed);
        }
    }

    private Path pathFor(UUID id) {
        // A UUID's string form contains only hex and hyphens, so this cannot escape the directory.
        // Resolved and re-checked anyway, because "cannot" is a claim worth making the code state.
        Path resolved = directory.resolve(id.toString()).normalize();
        if (!resolved.startsWith(directory)) {
            throw new IllegalArgumentException(what + " id resolved outside the store: " + id);
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
