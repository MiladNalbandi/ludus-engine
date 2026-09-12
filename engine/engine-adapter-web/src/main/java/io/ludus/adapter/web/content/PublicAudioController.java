// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.AudioLibrary;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.AudioClipId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.io.InputStream;
import java.io.OutputStream;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * Serving audio to a game client.
 *
 * <p>{@link StreamingResponseBody} rather than a byte array or a {@code Resource} that gets
 * buffered: the container writes the clip out in chunks as it reads them, so a request costs a
 * buffer rather than a copy of the file. Ten players starting a level at once is ten buffers.
 *
 * <p>Audio is immutable once uploaded — a new upload is a new id — so it is cached hard and
 * needs no revalidation. That is the one thing here that differs from wave documents, which change
 * under a stable id and therefore need an {@code ETag}.
 */
@RestController
@RequestMapping("/api/v1/public/audio")
@Tag(name = "Public content")
class PublicAudioController {

    /** A year. Immutable content addressed by a random id cannot go stale. */
    private static final long IMMUTABLE_SECONDS = 31_536_000L;

    private final AudioLibrary audio;
    private final ActiveProject activeProject;

    PublicAudioController(AudioLibrary audio, ActiveProject activeProject) {
        this.audio = audio;
        this.activeProject = activeProject;
    }

    @GetMapping("/{id}")
    @Operation(
            summary = "Stream an audio clip",
            description =
                    "Cached immutably: a clip never changes under its id, so a client that has it"
                            + " never asks again.")
    ResponseEntity<StreamingResponseBody> stream(@PathVariable String id) {
        AudioClipId clipId;
        try {
            clipId = AudioClipId.of(id);
        } catch (IllegalArgumentException notAnId) {
            // Same answer as a clip that does not exist. A malformed id is not worth a distinct
            // response, and telling them apart tells a caller which ids are shaped correctly.
            return ResponseEntity.notFound().build();
        }

        return audio.open(activeProject.id(), clipId)
                .map(
                        streamed ->
                                ResponseEntity.ok()
                                        .contentType(MediaType.parseMediaType(streamed.clip().contentType()))
                                        .contentLength(streamed.clip().sizeBytes())
                                        .cacheControl(
                                                CacheControl.maxAge(
                                                                IMMUTABLE_SECONDS,
                                                                java.util.concurrent.TimeUnit.SECONDS)
                                                        .cachePublic()
                                                        .immutable())
                                        .header(
                                                HttpHeaders.CONTENT_DISPOSITION,
                                                "inline; filename=\""
                                                        + streamed.clip().filename().replace("\"", "")
                                                        + "\"")
                                        .body(copying(streamed.bytes())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    /**
     * Copies the stream through and closes it, whatever happens.
     *
     * <p>The try-with-resources matters more than it looks: a client that disconnects mid-download
     * throws out of {@code transferTo}, and without this every abandoned download would leak a file
     * handle until the process ran out of them.
     */
    private StreamingResponseBody copying(InputStream bytes) {
        return (OutputStream out) -> {
            try (InputStream source = bytes) {
                source.transferTo(out);
            }
        };
    }
}
