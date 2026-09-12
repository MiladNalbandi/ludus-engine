// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.AudioClipRepository;
import io.ludus.application.content.port.out.AudioStore;
import io.ludus.domain.content.AudioClip;
import io.ludus.domain.content.AudioClipId;
import io.ludus.domain.project.ProjectId;
import java.io.InputStream;
import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Uploading, listing, streaming and removing audio.
 *
 * <p>Two stores, deliberately: metadata in the database, bytes behind {@link AudioStore}. Keeping
 * them apart is what lets a list of forty clips be one query that touches no files, and it is why
 * nothing here returns a byte array.
 *
 * <p>The pair can come apart — bytes written and then the metadata insert failing, or the reverse —
 * so both directions are handled rather than assumed. Bytes without metadata are invisible and get
 * cleaned up on the next upload attempt with the same id (there is not one, ids are random, so in
 * practice they are simply orphaned); metadata without bytes is reported as a missing clip rather
 * than a 500.
 */
public class AudioLibrary {

    /**
     * What may be uploaded, as an allow-list.
     *
     * <p>An allow-list rather than a deny-list, because the interesting content types are the ones
     * nobody thought of. These are stored and served back with the type they were uploaded as, so
     * accepting {@code text/html} would turn this into a way to host a page on the engine's origin.
     */
    private static final Set<String> ALLOWED_CONTENT_TYPES =
            Set.of("audio/mpeg", "audio/ogg", "audio/wav", "audio/x-wav", "audio/webm", "audio/aac", "audio/flac");

    private final AudioClipRepository clips;
    private final AudioStore store;
    private final Clock clock;

    public AudioLibrary(AudioClipRepository clips, AudioStore store, Clock clock) {
        this.clips = clips;
        this.store = store;
        this.clock = clock;
    }

    /**
     * Streams an upload into storage and records it.
     *
     * <p>The size is what the store actually wrote, not a length the client declared. A client that
     * lies about its content length should not be able to make the catalogue lie too.
     */
    public AudioClip upload(
            ProjectId projectId, String filename, String contentType, InputStream bytes) {

        String type = normalise(contentType);
        if (!ALLOWED_CONTENT_TYPES.contains(type)) {
            throw new ContentRejected(
                    List.of(
                            new ContentViolation(
                                    "/contentType",
                                    "'" + type + "' is not an accepted audio type; expected one of "
                                            + ALLOWED_CONTENT_TYPES.stream().sorted().toList())));
        }

        AudioClipId id = AudioClipId.random();
        long written = store.store(id, bytes);
        if (written <= 0) {
            store.delete(id);
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("the uploaded file was empty")));
        }

        return clips.save(
                new AudioClip(id, projectId, filename, type, written, clock.instant()));
    }

    public List<AudioClip> list(ProjectId projectId) {
        return clips.list(projectId);
    }

    public Optional<AudioClip> find(ProjectId projectId, AudioClipId id) {
        return clips.find(projectId, id);
    }

    /**
     * Opens a clip for streaming, scoped to a project.
     *
     * <p>Returns both parts so a caller can set the content type and length without a second
     * lookup, and empty if either half is missing.
     */
    public Optional<Streamed> open(ProjectId projectId, AudioClipId id) {
        return clips.find(projectId, id)
                .flatMap(clip -> store.open(id).map(bytes -> new Streamed(clip, bytes)));
    }

    /** Removes metadata first, then bytes: a clip nobody can find is better than bytes nobody owns. */
    public boolean delete(ProjectId projectId, AudioClipId id) {
        if (!clips.delete(projectId, id)) {
            return false;
        }
        store.delete(id);
        return true;
    }

    private String normalise(String contentType) {
        if (contentType == null || contentType.isBlank()) {
            return "";
        }
        // "audio/mpeg; charset=binary" is a thing browsers send.
        return contentType.split(";")[0].trim().toLowerCase(java.util.Locale.ROOT);
    }

    /** A clip and an open stream of its bytes. The caller closes the stream. */
    public record Streamed(AudioClip clip, InputStream bytes) {}
}
