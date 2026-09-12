// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.adapter.persistence.project.ProjectRepositoryAdapter;
import io.ludus.application.content.port.out.WaveLevelRepository;
import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

/**
 * The rules wave levels exist to make structural, checked against a real schema.
 *
 * <p>All four of these were application logic in the codebase Ludus was extracted from, and each
 * was wrong there at least once — a second active level after a failed request, memberships left
 * pointing at deleted waves, a level in one project quietly referencing another's content. The
 * point of this file is that none of them can be reintroduced by a new code path, because none of
 * them is enforced by code.
 *
 * <p>Two projects exist throughout, deliberately. A repository that ignores its project argument
 * passes every single-project test ever written.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({
    ProjectRepositoryAdapter.class,
    WaveRepositoryAdapter.class,
    WaveLevelRepositoryAdapter.class
})
class WaveLevelConstraintsTest {

    private static final Instant NOW = Instant.parse("2026-09-12T09:00:00Z");

    @Autowired private ProjectRepository projects;
    @Autowired private WaveRepository waves;
    @Autowired private WaveLevelRepository levels;
    @Autowired private TestEntityManager entityManager;

    private ProjectId mine;
    private ProjectId theirs;

    @BeforeEach
    void twoProjects() {
        mine = projects.save(Project.create(new Slug("mine"), "Mine", NOW)).id();
        theirs = projects.save(Project.create(new Slug("theirs"), "Theirs", NOW)).id();
        flush();
    }

    private void flush() {
        entityManager.flush();
        entityManager.clear();
    }

    private Slug wave(ProjectId project, String id, int order) {
        waves.save(
                Wave.draft(
                        project,
                        new Slug(id),
                        id,
                        order,
                        1,
                        "https://ludus.dev/schemas/wave/v1.json",
                        new ContentBody("{\"id\":\"" + id + "\"}"),
                        NOW));
        flush();
        return new Slug(id);
    }

    private WaveLevel level(ProjectId project, String name, List<Slug> members) {
        WaveLevel saved =
                levels.save(
                        WaveLevel.create(
                                WaveLevelId.random(), project, name, null, members, NOW));
        flush();
        return saved;
    }

    @Test
    void the_order_of_the_waves_in_a_level_is_the_order_they_come_back_in() {
        Slug third = wave(mine, "c_last", 2);
        Slug first = wave(mine, "a_first", 0);
        Slug second = wave(mine, "b_middle", 1);

        WaveLevel saved = level(mine, "Act One", List.of(third, first, second));

        assertThat(levels.find(mine, saved.id()).orElseThrow().waves())
                .as("the list order is the level's order, not the waves' own or the database's")
                .containsExactly(third, first, second);
    }

    @Test
    void resequencing_a_level_replaces_its_order_rather_than_appending_to_it() {
        Slug a = wave(mine, "a", 0);
        Slug b = wave(mine, "b", 1);
        WaveLevel saved = level(mine, "Act One", List.of(a, b));

        levels.save(saved.with("Act One", null, List.of(b, a), NOW));
        flush();

        assertThat(levels.find(mine, saved.id()).orElseThrow().waves()).containsExactly(b, a);
    }

    @Test
    void a_project_can_only_ever_have_one_active_level() {
        Slug a = wave(mine, "a", 0);
        WaveLevel first = level(mine, "First", List.of(a));
        WaveLevel second = level(mine, "Second", List.of(a));

        levels.activate(mine, first.id(), NOW);
        flush();
        levels.activate(mine, second.id(), NOW);
        flush();

        assertThat(levels.findActive(mine))
                .as("activating replaces; the primary key on project_id leaves nowhere for a second row")
                .get()
                .extracting(WaveLevel::id)
                .isEqualTo(second.id());
        assertThat(entityManager.getEntityManager()
                        .createQuery("select count(a) from WaveLevelActivationEntity a", Long.class)
                        .getSingleResult())
                .isEqualTo(1L);
    }

    @Test
    void activating_in_one_project_does_not_touch_another() {
        Slug mineWave = wave(mine, "a", 0);
        Slug theirWave = wave(theirs, "a", 0);
        WaveLevel ours = level(mine, "Ours", List.of(mineWave));
        WaveLevel theirLevel = level(theirs, "Theirs", List.of(theirWave));

        levels.activate(mine, ours.id(), NOW);
        levels.activate(theirs, theirLevel.id(), NOW);
        flush();

        assertThat(levels.findActive(mine)).get().extracting(WaveLevel::id).isEqualTo(ours.id());
        assertThat(levels.findActive(theirs))
                .get()
                .extracting(WaveLevel::id)
                .isEqualTo(theirLevel.id());
    }

    @Test
    void deleting_a_wave_removes_it_from_every_level_that_used_it() {
        Slug keep = wave(mine, "keep", 0);
        Slug doomed = wave(mine, "doomed", 1);
        WaveLevel saved = level(mine, "Act One", List.of(keep, doomed));

        waves.delete(mine, doomed);
        flush();

        assertThat(levels.find(mine, saved.id()).orElseThrow().waves())
                .as("the cascade is a foreign key, so no delete path can forget it")
                .containsExactly(keep);
    }

    @Test
    void deleting_the_active_level_leaves_the_project_with_none_rather_than_a_dangling_pointer() {
        Slug a = wave(mine, "a", 0);
        WaveLevel saved = level(mine, "Act One", List.of(a));
        levels.activate(mine, saved.id(), NOW);
        flush();

        assertThat(levels.delete(mine, saved.id())).isTrue();
        flush();

        assertThat(levels.findActive(mine)).isEmpty();
    }

    @Test
    void a_level_cannot_be_read_or_deleted_from_another_project() {
        Slug a = wave(mine, "a", 0);
        WaveLevel saved = level(mine, "Act One", List.of(a));

        assertThat(levels.find(theirs, saved.id())).isEmpty();
        assertThat(levels.delete(theirs, saved.id())).isFalse();
        assertThat(levels.find(mine, saved.id())).isPresent();
    }

    @Test
    void a_level_cannot_contain_a_wave_from_another_project() {
        Slug notMine = wave(theirs, "theirs_only", 0);

        // The application layer checks this first and returns a friendly 422. This asserts the
        // floor underneath that check: even reaching the database directly, the composite foreign
        // key refuses the row.
        assertThatThrownBy(() -> level(mine, "Act One", List.of(notMine)))
                .as("the membership row references (project_id, wave_id), so it cannot cross projects")
                .isInstanceOf(Exception.class);
    }
}
