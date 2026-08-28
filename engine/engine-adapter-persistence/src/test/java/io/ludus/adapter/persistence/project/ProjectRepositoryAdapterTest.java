// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.project;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatException;

import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

/**
 * Exercises the adapter against the migration that ships, not a Hibernate-generated schema.
 *
 * <p>Every assertion that claims something about the database is preceded by a flush and a clear.
 * Without them the reads are answered from the persistence context and the test passes whatever
 * the SQL says — a slice test that only proves the entity agrees with itself.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(ProjectRepositoryAdapter.class)
class ProjectRepositoryAdapterTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");

    @Autowired
    private ProjectRepository projects;

    @Autowired
    private TestEntityManager entityManager;

    private void reachTheDatabase() {
        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void a_saved_project_comes_back_by_id_and_by_slug() {
        Project saved = projects.save(Project.create(new Slug("default"), "Default", NOW));
        reachTheDatabase();

        assertThat(projects.findById(saved.id())).contains(saved);
        assertThat(projects.findBySlug(new Slug("default"))).contains(saved);
        assertThat(projects.count()).isEqualTo(1);
    }

    @Test
    void an_unknown_project_is_absent_rather_than_an_error() {
        assertThat(projects.findById(ProjectId.random())).isEmpty();
        assertThat(projects.findBySlug(new Slug("no_such_project"))).isEmpty();
    }

    /**
     * The database keeps microseconds and {@link Instant} keeps nanoseconds. Without the
     * truncation in the entity, the object handed back from {@code save} would stop being equal
     * to itself after the next restart — the sort of difference that surfaces as one failing
     * assertion in an unrelated test months later.
     */
    @Test
    void a_timestamp_survives_the_round_trip_unchanged() {
        Instant withNanos = NOW.plusNanos(123_456_789);

        Project saved = projects.save(Project.create(new Slug("precision"), "Precision", withNanos));
        reachTheDatabase();

        assertThat(saved.createdAt()).isEqualTo(withNanos.truncatedTo(ChronoUnit.MICROS));
        assertThat(projects.findById(saved.id()).orElseThrow().createdAt())
                .isEqualTo(saved.createdAt());
    }

    @Test
    void two_projects_cannot_share_a_slug() {
        projects.save(Project.create(new Slug("default"), "Default", NOW));
        reachTheDatabase();

        projects.save(Project.create(new Slug("default"), "Again", NOW));

        assertThatException()
                .as("uq_project_slug must reject the second insert")
                .isThrownBy(() -> entityManager.flush());
    }
}
