// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

/**
 * Assembling levels, without a database.
 *
 * <p>What the constraint test proves about the schema, this proves about the answers an author
 * gets: which index of their list was wrong, and what a game client is served when a level is half
 * published.
 */
class WaveLevelsTest {

    private static final Instant NOW = Instant.parse("2026-09-12T10:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final ProjectId THEIRS = ProjectId.random();

    private final ContentFakes.Waves waves = new ContentFakes.Waves();
    private final ContentFakes.Levels levels = new ContentFakes.Levels();
    private final WaveLevels waveLevels =
            new WaveLevels(levels, waves, Clock.fixed(NOW, ZoneOffset.UTC));

    private Slug wave(ProjectId project, String id, boolean published) {
        Wave draft =
                Wave.draft(
                        project,
                        new Slug(id),
                        id,
                        waves.list(project).size(),
                        1,
                        "https://ludus.dev/schemas/wave/v1.json",
                        new ContentBody("{\"id\":\"" + id + "\"}"),
                        NOW);
        waves.save(published ? draft.published(true, NOW) : draft);
        return new Slug(id);
    }

    @Test
    void a_level_keeps_the_order_it_was_given() {
        Slug c = wave(MINE, "c", false);
        Slug a = wave(MINE, "a", false);

        WaveLevel created = waveLevels.create(MINE, "Act One", "the first act", List.of(c, a));

        assertThat(created.waves()).containsExactly(c, a);
        assertThat(created.description()).isEqualTo("the first act");
    }

    @Test
    void every_wave_that_is_not_there_is_reported_at_the_index_that_named_it() {
        Slug real = wave(MINE, "real", false);

        assertThatThrownBy(
                        () ->
                                waveLevels.create(
                                        MINE,
                                        "Act One",
                                        null,
                                        List.of(new Slug("ghost"), real, new Slug("phantom"))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .as("all of them at once, each at its own index")
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/waves/0", "/waves/2"));
    }

    @Test
    void a_wave_from_another_project_is_reported_as_missing_rather_than_accepted() {
        Slug notMine = wave(THEIRS, "theirs", false);

        assertThatThrownBy(() -> waveLevels.create(MINE, "Act One", null, List.of(notMine)))
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void a_malformed_entry_is_a_violation_rather_than_an_exception() {
        // The controller turns anything that is not a valid slug into a null, because a slug that
        // cannot exist cannot name a wave that exists. It must arrive as a 422 at its index.
        assertThatThrownBy(
                        () -> waveLevels.create(MINE, "Act One", null, Arrays.asList((Slug) null)))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/waves/0"));
    }

    @Test
    void a_level_needs_a_name() {
        assertThatThrownBy(() -> waveLevels.create(MINE, "  ", null, List.of()))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/name"));
    }

    @Test
    void an_empty_level_is_allowed_because_one_is_assembled_before_it_is_filled() {
        assertThat(waveLevels.create(MINE, "Act One", null, List.of()).waves()).isEmpty();
    }

    @Test
    void a_level_cannot_list_the_same_wave_twice() {
        Slug a = wave(MINE, "a", false);

        assertThatThrownBy(() -> waveLevels.create(MINE, "Act One", null, List.of(a, a)))
                .as("two slots that advance together make a progress counter that cannot be right")
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void creating_a_level_does_not_activate_it() {
        Slug a = wave(MINE, "a", true);
        waveLevels.create(MINE, "Act One", null, List.of(a));

        assertThat(waveLevels.active(MINE)).isEmpty();
    }

    @Test
    void activating_something_that_is_not_there_is_false_rather_than_an_error() {
        assertThat(waveLevels.activate(MINE, WaveLevelId.random())).isFalse();
        assertThat(waveLevels.active(MINE)).isEmpty();
    }

    @Test
    void a_client_is_served_only_the_published_members_in_order() {
        Slug first = wave(MINE, "first", true);
        Slug middle = wave(MINE, "middle", false);
        Slug last = wave(MINE, "last", true);

        WaveLevel level = waveLevels.create(MINE, "Act One", null, List.of(first, middle, last));
        waveLevels.activate(MINE, level.id());

        assertThat(waveLevels.activeForPlayers(MINE))
                .get()
                .extracting(WaveLevels.PlayableLevel::waves)
                .satisfies(
                        played ->
                                assertThat(played)
                                        .as("the draft is absent, and the rest keep their order")
                                        .extracting("id")
                                        .containsExactly(first, last));
    }

    @Test
    void no_active_level_is_empty_rather_than_an_empty_level() {
        wave(MINE, "a", true);

        assertThat(waveLevels.activeForPlayers(MINE))
                .as("a client must be able to tell 'nothing chosen' from 'chosen and empty'")
                .isEmpty();
    }

    @Test
    void updating_replaces_the_sequence_rather_than_adding_to_it() {
        Slug a = wave(MINE, "a", false);
        Slug b = wave(MINE, "b", false);
        WaveLevel level = waveLevels.create(MINE, "Act One", null, List.of(a, b));

        WaveLevel updated =
                waveLevels.update(MINE, level.id(), "Act Two", "revised", List.of(b)).orElseThrow();

        assertThat(updated.waves()).containsExactly(b);
        assertThat(updated.name()).isEqualTo("Act Two");
        assertThat(updated.createdAt()).isEqualTo(level.createdAt());
    }

    @Test
    void a_level_belonging_to_another_project_is_not_found_by_any_route() {
        Slug a = wave(MINE, "a", false);
        WaveLevel level = waveLevels.create(MINE, "Act One", null, List.of(a));

        assertThat(waveLevels.find(THEIRS, level.id())).isEmpty();
        assertThat(waveLevels.update(THEIRS, level.id(), "Hijacked", null, List.of())).isEmpty();
        assertThat(waveLevels.delete(THEIRS, level.id())).isFalse();
        assertThat(waveLevels.activate(THEIRS, level.id())).isFalse();
    }
}
