// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.AudioLibrary;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.AudioClipId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.io.InputStream;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * Uploading and managing audio. Editors and above.
 *
 * <p>The upload is taken as a {@link MultipartFile} and its {@link MultipartFile#getInputStream()}
 * handed straight through. Nothing here calls {@code getBytes()} — that would materialise the whole
 * clip in heap, which is the exact regression the streaming design exists to prevent.
 */
@RestController
@RequestMapping("/api/v1/admin/audio")
@Tag(name = "Audio")
class AudioAdminController {

    private final AudioLibrary audio;
    private final ActiveProject activeProject;

    AudioAdminController(AudioLibrary audio, ActiveProject activeProject) {
        this.audio = audio;
        this.activeProject = activeProject;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(operationId = "uploadAudioClip",
            summary = "Upload an audio clip",
            description =
                    "Streamed to storage; the recorded size is what was actually written, not a"
                            + " length the client declared.")
    ResponseEntity<AudioDtos.Summary> upload(@RequestParam("file") MultipartFile file) {
        try (InputStream bytes = file.getInputStream()) {
            return ResponseEntity.status(HttpStatus.CREATED)
                    .body(
                            AudioDtos.Summary.of(
                                    audio.upload(
                                            activeProject.id(),
                                            filenameOf(file),
                                            file.getContentType(),
                                            bytes)));
        } catch (IOException unreadable) {
            throw new UncheckedIOException("could not read the uploaded file", unreadable);
        }
    }

    @GetMapping
    @Operation(operationId = "listAudioClips", summary = "List audio clips. Metadata only; no file is opened.")
    List<AudioDtos.Summary> list() {
        return audio.list(activeProject.id()).stream().map(AudioDtos.Summary::of).toList();
    }

    @DeleteMapping("/{id}")
    @Operation(operationId = "deleteAudioClip", summary = "Delete a clip and its bytes")
    ResponseEntity<Void> delete(@PathVariable String id) {
        return audio.delete(activeProject.id(), AudioClipId.of(id))
                ? ResponseEntity.noContent().build()
                : ResponseEntity.notFound().build();
    }

    /**
     * A filename is a label here, never a path — clips are stored under their id. It is still
     * reduced to its last segment, because storing {@code ../../etc/passwd} as a display name is
     * an invitation for some later reader to treat it as one.
     */
    private String filenameOf(MultipartFile file) {
        String submitted = file.getOriginalFilename();
        if (submitted == null || submitted.isBlank()) {
            return "untitled";
        }
        String leaf = submitted.replace('\\', '/');
        leaf = leaf.substring(leaf.lastIndexOf('/') + 1);
        return leaf.isBlank() ? "untitled" : leaf;
    }
}
