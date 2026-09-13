// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.port.out.AudioClipRepository;
import io.ludus.application.content.port.out.AudioMixer;
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

/**
 * Mixing, at the application layer.
 *
 * <p>The assertions worth the file are about what the mixer is <em>not</em> given: a clip from
 * another project, an id it has no bytes for, or a filename. The adapter's job is to never build a
 * command string; this layer's job is to never hand it something it should not have.
 */
class AudioMixingTest {

    private static final Instant NOW = Instant.parse("2026-09-12T12:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final ProjectId THEIRS = ProjectId.random();

    private final Clips clips = new Clips();
    private final Store store = new Store();
    private final RecordingMixer mixer = new RecordingMixer();
    private final AudioLibrary audio =
            new AudioLibrary(clips, store, mixer, Clock.fixed(NOW, ZoneOffset.UTC));

    private AudioClip upload(ProjectId project, String name) {
        return audio.upload(
                project,
                name,
                "audio/ogg",
                new ByteArrayInputStream(name.getBytes(StandardCharsets.UTF_8)));
    }

    @Test
    void a_mix_is_an_ordinary_clip_afterwards() {
        AudioClip one = upload(MINE, "drums.ogg");
        AudioClip two = upload(MINE, "bass.ogg");

        AudioClip mixed =
                audio.mix(
                        MINE,
                        "loop.ogg",
                        List.of(
                                new AudioLibrary.MixTrack(one.id(), 0),
                                new AudioLibrary.MixTrack(two.id(), -3)));

        assertThat(audio.find(MINE, mixed.id()))
                .as("nothing has to remember it was produced rather than uploaded")
                .isPresent();
        assertThat(audio.open(MINE, mixed.id())).isPresent();
        assertThat(mixed.filename()).isEqualTo("loop.ogg");
    }

    @Test
    void the_gains_reach_the_mixer_in_the_order_given() {
        AudioClip one = upload(MINE, "a.ogg");
        AudioClip two = upload(MINE, "b.ogg");

        audio.mix(
                MINE,
                "loop.ogg",
                List.of(
                        new AudioLibrary.MixTrack(two.id(), -6),
                        new AudioLibrary.MixTrack(one.id(), 1.5)));

        assertThat(mixer.lastSources).extracting(AudioMixer.Source::gainDb).containsExactly(-6.0, 1.5);
        assertThat(mixer.lastSources)
                .extracting(AudioMixer.Source::id)
                .containsExactly(two.id(), one.id());
    }

    @Test
    void the_mixer_never_receives_a_filename() {
        AudioClip one = upload(MINE, "$(rm -rf /).ogg");

        audio.mix(MINE, "safe.ogg", List.of(new AudioLibrary.MixTrack(one.id(), 0)));

        // A Source carries an id and a stream. There is no field a filename could travel in, which
        // is the structural half of the reason the adapter cannot be talked into running one. The
        // predecessor interpolated uploaded filenames into a shell command.
        assertThat(AudioMixer.Source.class.getRecordComponents())
                .extracting(java.lang.reflect.RecordComponent::getName)
                .containsExactlyInAnyOrder("id", "bytes", "gainDb");
    }

    @Test
    void a_clip_from_another_project_is_reported_as_missing_rather_than_mixed() {
        AudioClip mine = upload(MINE, "mine.ogg");
        AudioClip theirs = upload(THEIRS, "theirs.ogg");

        assertThatThrownBy(
                        () ->
                                audio.mix(
                                        MINE,
                                        "loop.ogg",
                                        List.of(
                                                new AudioLibrary.MixTrack(mine.id(), 0),
                                                new AudioLibrary.MixTrack(theirs.id(), 0))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/tracks/1"));

        assertThat(mixer.calls).as("the mixer is not run at all when a track is refused").isZero();
    }

    @Test
    void every_unknown_track_is_reported_at_its_own_index() {
        AudioClip real = upload(MINE, "real.ogg");

        assertThatThrownBy(
                        () ->
                                audio.mix(
                                        MINE,
                                        "loop.ogg",
                                        List.of(
                                                new AudioLibrary.MixTrack(AudioClipId.random(), 0),
                                                new AudioLibrary.MixTrack(real.id(), 0),
                                                new AudioLibrary.MixTrack(null, 0))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/tracks/0", "/tracks/2"));
    }

    @Test
    void a_rejected_mix_closes_every_stream_it_opened() {
        AudioClip one = upload(MINE, "a.ogg");
        AudioClip two = upload(MINE, "b.ogg");

        assertThatThrownBy(
                        () ->
                                audio.mix(
                                        MINE,
                                        "loop.ogg",
                                        List.of(
                                                new AudioLibrary.MixTrack(one.id(), 0),
                                                new AudioLibrary.MixTrack(two.id(), 0),
                                                new AudioLibrary.MixTrack(AudioClipId.random(), 0))))
                .isInstanceOf(ContentRejected.class);

        // Without this, a request naming one missing clip among five leaks four open files -- and
        // it leaks them on the path a caller can trigger at will.
        assertThat(store.openStreams()).as("open streams after a refused mix").isZero();
    }

    @Test
    void an_empty_track_list_is_refused_before_the_mixer_is_asked() {
        assertThatThrownBy(() -> audio.mix(MINE, "loop.ogg", List.of()))
                .isInstanceOf(ContentRejected.class);
        assertThatThrownBy(() -> audio.mix(MINE, "loop.ogg", null))
                .isInstanceOf(ContentRejected.class);
        assertThat(mixer.calls).isZero();
    }

    @Test
    void a_mixer_failure_is_not_turned_into_a_stored_clip() {
        AudioClip one = upload(MINE, "a.ogg");
        mixer.failWith = "the mixer refused those tracks";
        int before = audio.list(MINE).size();

        assertThatThrownBy(() -> audio.mix(MINE, "loop.ogg", List.of(new AudioLibrary.MixTrack(one.id(), 0))))
                .isInstanceOf(AudioMixer.MixFailed.class);

        assertThat(audio.list(MINE)).hasSize(before);
    }

    @Test
    void canMix_reports_what_the_install_can_actually_do() {
        assertThat(audio.canMix()).isTrue();
        mixer.availableNow = false;
        assertThat(audio.canMix()).isFalse();
    }

    // ------------------------------------------------------------------ fakes

    private final class RecordingMixer implements AudioMixer {
        private List<Source> lastSources = List.of();
        private int calls;
        private boolean availableNow = true;
        private String failWith;

        @Override
        public boolean available() {
            return availableNow;
        }

        @Override
        public Mixed mix(List<Source> sources) {
            calls++;
            lastSources = new ArrayList<>(sources);
            if (failWith != null) {
                throw new MixFailed(failWith);
            }
            return new Mixed(
                    new ByteArrayInputStream("mixed".getBytes(StandardCharsets.UTF_8)), "audio/ogg");
        }
    }

    /** Counts the streams it has handed out and not seen closed. */
    private final class Store implements AudioStore {
        private final Map<AudioClipId, byte[]> stored = new LinkedHashMap<>();
        private int open;

        private int openStreams() {
            return open;
        }

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
            byte[] content = stored.get(id);
            if (content == null) {
                return Optional.empty();
            }
            open++;
            return Optional.of(
                    new java.io.FilterInputStream(new ByteArrayInputStream(content)) {
                        @Override
                        public void close() throws IOException {
                            open--;
                            super.close();
                        }
                    });
        }

        @Override
        public boolean delete(AudioClipId id) {
            return stored.remove(id) != null;
        }
    }

    private static final class Clips implements AudioClipRepository {
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
            return find(projectId, id).isPresent() && byId.remove(id) != null;
        }
    }
}
