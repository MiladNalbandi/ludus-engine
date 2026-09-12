// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.port.out.AudioClipRepository;
import io.ludus.application.content.port.out.AudioStore;
import io.ludus.domain.content.AudioClip;
import io.ludus.domain.content.AudioClipId;
import io.ludus.domain.project.ProjectId;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * The branches {@code AudioStreamingIT} cannot reach.
 *
 * <p>That test proves the bytes never enter the heap, which needs a real server and a real disk and
 * takes seconds. Everything here is about what happens when something is wrong — a type that is not
 * audio, an empty upload, metadata whose bytes have gone missing — and none of it needs either.
 */
class AudioLibraryTest {

    private static final ProjectId PROJECT = ProjectId.random();
    private static final ProjectId OTHER_PROJECT = ProjectId.random();

    private final Clips clips = new Clips();
    private final Store store = new Store();
    private final AudioLibrary audio =
            new AudioLibrary(clips, store, Clock.fixed(Instant.parse("2026-09-12T10:00:00Z"), ZoneOffset.UTC));

    private static InputStream bytes(String content) {
        return new ByteArrayInputStream(content.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void an_upload_records_what_was_actually_written_not_what_was_claimed() {
        AudioClip clip = audio.upload(PROJECT, "theme.ogg", "audio/ogg", bytes("twelve bytes"));

        assertThat(clip.sizeBytes())
                .as("the size is what the store wrote, so a lying client cannot make the catalogue lie")
                .isEqualTo(12);
        assertThat(clip.filename()).isEqualTo("theme.ogg");
        assertThat(clip.createdAt()).isEqualTo(Instant.parse("2026-09-12T10:00:00Z"));
        assertThat(clips.find(PROJECT, clip.id())).isPresent();
    }

    @ParameterizedTest
    @ValueSource(strings = {"audio/mpeg; charset=binary", "AUDIO/OGG", " audio/wav "})
    void a_content_type_is_normalised_before_it_is_checked(String type) {
        assertThat(audio.upload(PROJECT, "clip", type, bytes("x")).contentType())
                .doesNotContain(";")
                .isLowerCase()
                .isNotBlank();
    }

    @ParameterizedTest
    @ValueSource(strings = {"text/html", "application/octet-stream", "image/svg+xml", ""})
    void anything_that_is_not_audio_is_refused(String type) {
        assertThatThrownBy(() -> audio.upload(PROJECT, "payload", type, bytes("<script>")))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        rejected ->
                                assertThat(((ContentRejected) rejected).violations())
                                        .singleElement()
                                        .extracting(ContentViolation::pointer)
                                        .isEqualTo("/contentType"));

        assertThat(store.stored)
                .as("a refused type must not reach storage at all")
                .isEmpty();
    }

    @Test
    void a_null_content_type_is_refused_rather_than_throwing() {
        assertThatThrownBy(() -> audio.upload(PROJECT, "clip", null, bytes("x")))
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void an_empty_upload_is_refused_and_leaves_nothing_behind() {
        assertThatThrownBy(() -> audio.upload(PROJECT, "silence.ogg", "audio/ogg", bytes("")))
                .isInstanceOf(ContentRejected.class);

        assertThat(store.stored)
                .as("the zero-byte file is deleted again; orphaned bytes nobody can find are worse than none")
                .isEmpty();
        assertThat(clips.list(PROJECT))
                .as("and no metadata row is written for a clip that does not exist")
                .isEmpty();
    }

    @Test
    void a_clip_whose_bytes_have_gone_missing_reads_as_absent_rather_than_failing() {
        AudioClip clip = audio.upload(PROJECT, "theme.ogg", "audio/ogg", bytes("some audio"));
        store.stored.clear(); // the volume was not mounted on this deploy

        assertThat(audio.find(PROJECT, clip.id()))
                .as("the metadata is still there, and listing must keep working")
                .isPresent();
        assertThat(audio.open(PROJECT, clip.id()))
                .as("but opening it is a miss, not a 500")
                .isEmpty();
    }

    @Test
    void one_project_cannot_open_or_delete_another_projects_clip() {
        AudioClip clip = audio.upload(PROJECT, "theme.ogg", "audio/ogg", bytes("some audio"));

        assertThat(audio.find(OTHER_PROJECT, clip.id())).isEmpty();
        assertThat(audio.open(OTHER_PROJECT, clip.id())).isEmpty();
        assertThat(audio.delete(OTHER_PROJECT, clip.id())).isFalse();
        assertThat(store.stored)
                .as("a delete that found no metadata must not have removed the bytes")
                .containsKey(clip.id());
    }

    @Test
    void deleting_removes_the_metadata_before_the_bytes() {
        AudioClip clip = audio.upload(PROJECT, "theme.ogg", "audio/ogg", bytes("some audio"));

        assertThat(audio.delete(PROJECT, clip.id())).isTrue();
        assertThat(clips.find(PROJECT, clip.id())).isEmpty();
        assertThat(store.stored).doesNotContainKey(clip.id());
        assertThat(order)
                .as("metadata first: a clip nobody can find beats bytes nobody owns")
                .containsExactly("delete-metadata", "delete-bytes");
    }

    @Test
    void deleting_something_that_is_not_there_is_false_rather_than_an_error() {
        assertThat(audio.delete(PROJECT, AudioClipId.random())).isFalse();
    }

    @Test
    void listing_is_scoped_to_the_project() {
        audio.upload(PROJECT, "a.ogg", "audio/ogg", bytes("a"));
        audio.upload(PROJECT, "b.ogg", "audio/ogg", bytes("b"));
        audio.upload(OTHER_PROJECT, "c.ogg", "audio/ogg", bytes("c"));

        assertThat(audio.list(PROJECT)).hasSize(2);
        assertThat(audio.list(OTHER_PROJECT)).hasSize(1);
    }

    /** An in-memory store. Small strings only — the heap behaviour is {@code AudioStreamingIT}'s job. */
    private final class Store implements AudioStore {
        private final Map<AudioClipId, byte[]> stored = new LinkedHashMap<>();

        @Override
        public long store(AudioClipId id, InputStream in) {
            try {
                byte[] content = in.readAllBytes();
                stored.put(id, content);
                return content.length;
            } catch (IOException e) {
                throw new IllegalStateException(e);
            }
        }

        @Override
        public Optional<InputStream> open(AudioClipId id) {
            return Optional.ofNullable(stored.get(id)).map(ByteArrayInputStream::new);
        }

        @Override
        public boolean delete(AudioClipId id) {
            order.add("delete-bytes");
            return stored.remove(id) != null;
        }
    }

    /** Records the order of the two deletes, because the ordering is the invariant. */
    private final List<String> order = new ArrayList<>();

    private final class Clips implements AudioClipRepository {
        private final Map<AudioClipId, AudioClip> byId = new LinkedHashMap<>();

        @Override
        public AudioClip save(AudioClip clip) {
            byId.put(clip.id(), clip);
            return clip;
        }

        @Override
        public Optional<AudioClip> find(ProjectId projectId, AudioClipId id) {
            return Optional.ofNullable(byId.get(id)).filter(c -> c.projectId().equals(projectId));
        }

        @Override
        public List<AudioClip> list(ProjectId projectId) {
            return byId.values().stream().filter(c -> c.projectId().equals(projectId)).toList();
        }

        @Override
        public boolean delete(ProjectId projectId, AudioClipId id) {
            if (find(projectId, id).isEmpty()) {
                return false;
            }
            order.add("delete-metadata");
            byId.remove(id);
            return true;
        }
    }
}
