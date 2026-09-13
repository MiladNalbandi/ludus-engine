// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.port.out.SpriteRepository;
import io.ludus.application.player.port.out.SpriteStore;
import io.ludus.domain.player.Sprite;
import io.ludus.domain.player.SpriteId;
import io.ludus.domain.project.ProjectId;
import java.io.InputStream;
import java.time.Clock;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * Uploading and serving item art.
 *
 * <p>The same two-store shape as audio: metadata in the database, bytes behind a port. The pair can
 * come apart in either direction, so both are handled rather than assumed.
 *
 * <p>Content types are an allow-list, and a short one. Sprites are served back with the type they
 * were uploaded as, so accepting {@code image/svg+xml} would be accepting a document that can carry
 * script and have it run on the engine's own origin — which is why SVG is <b>not</b> on this list
 * despite being an obvious thing to want for game art. A project that needs vector art can serve it
 * from somewhere that is not this origin; {@code spriteRef} is deliberately an opaque reference and
 * a URL is a perfectly good one.
 */
public class SpriteLibrary {

    /**
     * Raster formats only, and no SVG.
     *
     * <p>SVG is XML that may contain {@code <script>}, and a browser rendering one served from this
     * origin runs it there. Stripping script from SVG reliably is a sanitiser's whole job, and
     * shipping one is a bigger commitment than declining the format.
     */
    private static final Set<String> ALLOWED_CONTENT_TYPES =
            Set.of("image/png", "image/jpeg", "image/webp", "image/gif");

    private final SpriteRepository sprites;
    private final SpriteStore store;
    private final Clock clock;

    public SpriteLibrary(SpriteRepository sprites, SpriteStore store, Clock clock) {
        this.sprites = sprites;
        this.store = store;
        this.clock = clock;
    }

    public Sprite upload(ProjectId projectId, String filename, String contentType, InputStream bytes) {
        String type = normalise(contentType);
        if (!ALLOWED_CONTENT_TYPES.contains(type)) {
            throw new ContentRejected(
                    List.of(
                            new ContentViolation(
                                    "/contentType",
                                    "'"
                                            + type
                                            + "' is not an accepted image type; expected one of "
                                            + ALLOWED_CONTENT_TYPES.stream().sorted().toList()
                                            + ". SVG is excluded deliberately: it can carry script,"
                                            + " and it would run on this engine's origin.")));
        }

        SpriteId id = SpriteId.random();
        long written = store.store(id, bytes);
        if (written <= 0) {
            store.delete(id);
            throw new ContentRejected(List.of(ContentViolation.atRoot("the uploaded file was empty")));
        }

        return sprites.save(
                new Sprite(id, projectId, filename, type, written, clock.instant()));
    }

    public List<Sprite> list(ProjectId projectId) {
        return sprites.list(projectId);
    }

    public Optional<Sprite> find(ProjectId projectId, SpriteId id) {
        return sprites.find(projectId, id);
    }

    /** Opens a sprite for streaming, scoped to a project. Empty if either half is missing. */
    public Optional<Streamed> open(ProjectId projectId, SpriteId id) {
        return sprites.find(projectId, id)
                .flatMap(sprite -> store.open(id).map(bytes -> new Streamed(sprite, bytes)));
    }

    /**
     * Removes a sprite.
     *
     * <p>Items referring to it are <b>not</b> changed, and are not checked for. {@code spriteRef} is
     * an opaque reference the game resolves — it may be a URL, an atlas key, or an id from
     * somewhere else entirely — so the engine has no list of what points at what, and inventing one
     * would mean pretending it owns a relationship it deliberately does not.
     */
    public boolean delete(ProjectId projectId, SpriteId id) {
        if (!sprites.delete(projectId, id)) {
            return false;
        }
        store.delete(id);
        return true;
    }

    private String normalise(String contentType) {
        if (contentType == null || contentType.isBlank()) {
            return "";
        }
        return contentType.split(";")[0].trim().toLowerCase(java.util.Locale.ROOT);
    }

    /** A sprite and an open stream of its bytes. The caller closes the stream. */
    public record Streamed(Sprite sprite, InputStream bytes) {}
}
