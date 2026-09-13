// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.port.out.SpriteRepository;
import io.ludus.application.player.port.out.SpriteStore;
import io.ludus.domain.player.Sprite;
import io.ludus.domain.player.SpriteId;
import io.ludus.domain.project.ProjectId;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * Sprite uploads, and the one refusal that is a security decision rather than tidiness.
 *
 * <p>SVG is excluded. It is XML that may contain {@code <script>}, and a browser rendering one
 * served from this origin runs it there — so accepting it would turn item art into stored
 * cross-site scripting against the editor and anything else on the same host.
 */
class SpriteLibraryTest {

    private static final Instant NOW = Instant.parse("2026-09-12T17:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final ProjectId THEIRS = ProjectId.random();

    private final Sprites sprites = new Sprites();
    private final Store store = new Store();
    private final SpriteLibrary library =
            new SpriteLibrary(sprites, store, Clock.fixed(NOW, ZoneOffset.UTC));

    private static InputStream bytes(String content) {
        return new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8));
    }

    @ParameterizedTest
    @ValueSource(strings = {"image/png", "image/jpeg", "image/webp", "image/gif", "IMAGE/PNG", "image/png; charset=binary"})
    void raster_images_are_accepted(String contentType) {
        assertThat(library.upload(MINE, "art.png", contentType, bytes("pixels")).contentType())
                .doesNotContain(";")
                .isLowerCase();
    }

    @ParameterizedTest
    @ValueSource(strings = {"image/svg+xml", "text/html", "application/xml", "application/octet-stream", ""})
    void anything_that_could_carry_script_is_refused(String contentType) {
        assertThatThrownBy(() -> library.upload(MINE, "art", contentType, bytes("<svg onload=...>")))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .singleElement()
                                        .extracting(ContentViolation::pointer)
                                        .isEqualTo("/contentType"));

        assertThat(store.stored).as("a refused type must not reach storage at all").isEmpty();
    }

    @Test
    void the_svg_refusal_explains_itself() {
        // The message matters here more than usual: SVG is the obvious format for game art, and an
        // author refused without a reason will assume it is an oversight and file a bug.
        assertThatThrownBy(() -> library.upload(MINE, "art.svg", "image/svg+xml", bytes("<svg/>")))
                .isInstanceOf(ContentRejected.class)
                .hasMessageContaining("rejected");
        assertThatThrownBy(() -> library.upload(MINE, "art.svg", "image/svg+xml", bytes("<svg/>")))
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations().get(0).message())
                                        .contains("script")
                                        .contains("origin"));
    }

    @Test
    void the_recorded_size_is_what_was_written_not_what_was_claimed() {
        assertThat(library.upload(MINE, "art.png", "image/png", bytes("twelve bytes")).sizeBytes())
                .isEqualTo(12);
    }

    @Test
    void an_empty_upload_is_refused_and_leaves_nothing_behind() {
        assertThatThrownBy(() -> library.upload(MINE, "art.png", "image/png", bytes("")))
                .isInstanceOf(ContentRejected.class);

        assertThat(store.stored).isEmpty();
        assertThat(library.list(MINE)).isEmpty();
    }

    @Test
    void a_sprite_whose_bytes_have_gone_missing_reads_as_absent_rather_than_failing() {
        Sprite sprite = library.upload(MINE, "art.png", "image/png", bytes("pixels"));
        store.stored.clear();

        assertThat(library.find(MINE, sprite.id())).isPresent();
        assertThat(library.open(MINE, sprite.id())).isEmpty();
    }

    @Test
    void one_project_cannot_read_or_delete_another_projects_sprite() {
        Sprite sprite = library.upload(MINE, "art.png", "image/png", bytes("pixels"));

        assertThat(library.find(THEIRS, sprite.id())).isEmpty();
        assertThat(library.open(THEIRS, sprite.id())).isEmpty();
        assertThat(library.delete(THEIRS, sprite.id())).isFalse();
        assertThat(store.stored).containsKey(sprite.id());
    }

    @Test
    void deleting_removes_the_metadata_and_the_bytes() {
        Sprite sprite = library.upload(MINE, "art.png", "image/png", bytes("pixels"));

        assertThat(library.delete(MINE, sprite.id())).isTrue();
        assertThat(library.find(MINE, sprite.id())).isEmpty();
        assertThat(store.stored).doesNotContainKey(sprite.id());
    }

    @Test
    void listing_is_scoped_to_the_project() {
        library.upload(MINE, "a.png", "image/png", bytes("a"));
        library.upload(THEIRS, "b.png", "image/png", bytes("b"));

        assertThat(library.list(MINE)).hasSize(1);
        assertThat(library.list(THEIRS)).hasSize(1);
    }

    private static final class Store implements SpriteStore {
        private final Map<SpriteId, byte[]> stored = new LinkedHashMap<>();

        @Override
        public long store(SpriteId id, InputStream in) {
            try {
                byte[] content = in.readAllBytes();
                stored.put(id, content);
                return content.length;
            } catch (IOException e) {
                throw new IllegalStateException(e);
            }
        }

        @Override
        public Optional<InputStream> open(SpriteId id) {
            return Optional.ofNullable(stored.get(id)).map(ByteArrayInputStream::new);
        }

        @Override
        public boolean delete(SpriteId id) {
            return stored.remove(id) != null;
        }
    }

    private static final class Sprites implements SpriteRepository {
        private final Map<SpriteId, Sprite> byId = new LinkedHashMap<>();

        @Override
        public Sprite save(Sprite sprite) {
            byId.put(sprite.id(), sprite);
            return sprite;
        }

        @Override
        public Optional<Sprite> find(ProjectId projectId, SpriteId id) {
            return Optional.ofNullable(byId.get(id)).filter(s -> s.projectId().equals(projectId));
        }

        @Override
        public List<Sprite> list(ProjectId projectId) {
            return byId.values().stream().filter(s -> s.projectId().equals(projectId)).toList();
        }

        @Override
        public boolean delete(ProjectId projectId, SpriteId id) {
            return find(projectId, id).isPresent() && byId.remove(id) != null;
        }
    }
}
