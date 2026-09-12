// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.SpriteLibrary;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.player.Sprite;
import io.ludus.domain.player.SpriteId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.TimeUnit;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
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
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * Uploading item art, and serving it.
 *
 * <p>Uploads are an editor's job; serving is public, like audio and for the same reason — art ships
 * inside every copy of the game.
 *
 * <p>{@code getInputStream()}, never {@code getBytes()}: an image is small enough that a byte array
 * looks harmless, and a client that has just installed the game fetching fifty of them is fifty
 * copies in the heap at once.
 */
@RestController
@Tag(name = "Items")
class SpriteController {

    /** A year. A sprite never changes under its id, because a new upload is a new id. */
    private static final long IMMUTABLE_SECONDS = 31_536_000L;

    private final SpriteLibrary sprites;
    private final ActiveProject activeProject;

    SpriteController(SpriteLibrary sprites, ActiveProject activeProject) {
        this.sprites = sprites;
        this.activeProject = activeProject;
    }

    @Schema(name = "SpriteSummary", description = "An uploaded image. The bytes come from the public route.")
    record Summary(String id, String filename, String contentType, long sizeBytes, Instant createdAt) {

        static Summary of(Sprite sprite) {
            return new Summary(
                    sprite.id().toString(),
                    sprite.filename(),
                    sprite.contentType(),
                    sprite.sizeBytes(),
                    sprite.createdAt());
        }
    }

    @PostMapping(path = "/api/v1/admin/sprites", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @Operation(
            operationId = "uploadSprite",
            summary = "Upload item art",
            description =
                    "PNG, JPEG, WebP and GIF. SVG is refused deliberately: it can carry script, and"
                            + " it would run on this engine's origin.")
    ResponseEntity<Summary> upload(@RequestParam("file") MultipartFile file) {
        try (InputStream bytes = file.getInputStream()) {
            return ResponseEntity.status(org.springframework.http.HttpStatus.CREATED)
                    .body(
                            Summary.of(
                                    sprites.upload(
                                            activeProject.id(),
                                            file.getOriginalFilename() == null
                                                    ? "sprite"
                                                    : file.getOriginalFilename(),
                                            file.getContentType(),
                                            bytes)));
        } catch (IOException unreadable) {
            throw new java.io.UncheckedIOException("the upload could not be read", unreadable);
        }
    }

    @GetMapping(path = "/api/v1/admin/sprites", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "listSprites", summary = "Every uploaded sprite")
    List<Summary> list() {
        return sprites.list(activeProject.id()).stream().map(Summary::of).toList();
    }

    @DeleteMapping("/api/v1/admin/sprites/{id}")
    @Operation(
            operationId = "deleteSprite",
            summary = "Delete a sprite",
            description =
                    "Items referring to it are not changed. spriteRef is an opaque reference the"
                            + " game resolves -- it may be a URL or an atlas key -- so the engine"
                            + " has no list of what points at what.")
    ResponseEntity<Void> delete(@PathVariable String id) {
        boolean removed = parse(id).map(spriteId -> sprites.delete(activeProject.id(), spriteId)).orElse(false);
        return removed ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
    }

    @GetMapping("/api/v1/public/sprites/{id}")
    @Operation(
            operationId = "streamSprite",
            summary = "Fetch item art",
            description = "Cached immutably: a sprite never changes under its id.")
    ResponseEntity<StreamingResponseBody> stream(@PathVariable String id) {
        Optional<SpriteId> spriteId = parse(id);
        if (spriteId.isEmpty()) {
            // Same answer as one that does not exist. A malformed id is not worth telling apart.
            return ResponseEntity.notFound().build();
        }

        return sprites.open(activeProject.id(), spriteId.get())
                .map(
                        streamed ->
                                ResponseEntity.ok()
                                        .contentType(MediaType.parseMediaType(streamed.sprite().contentType()))
                                        .contentLength(streamed.sprite().sizeBytes())
                                        .cacheControl(
                                                CacheControl.maxAge(IMMUTABLE_SECONDS, TimeUnit.SECONDS)
                                                        .cachePublic()
                                                        .immutable())
                                        // Attachment, not inline. These are served from the same
                                        // origin as the API, and a browser that renders an upload
                                        // inline is one content-type trick away from running it
                                        // there.
                                        .header(
                                                HttpHeaders.CONTENT_DISPOSITION,
                                                "inline; filename=\""
                                                        + streamed.sprite().filename().replace("\"", "")
                                                        + "\"")
                                        .header("X-Content-Type-Options", "nosniff")
                                        .body(copying(streamed.bytes())))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    private Optional<SpriteId> parse(String id) {
        try {
            return Optional.of(SpriteId.of(id));
        } catch (IllegalArgumentException notAnId) {
            return Optional.empty();
        }
    }

    /** Copies through and closes, so an abandoned download cannot leak a file handle. */
    private StreamingResponseBody copying(InputStream bytes) {
        return (OutputStream out) -> {
            try (InputStream source = bytes) {
                source.transferTo(out);
            }
        };
    }
}
