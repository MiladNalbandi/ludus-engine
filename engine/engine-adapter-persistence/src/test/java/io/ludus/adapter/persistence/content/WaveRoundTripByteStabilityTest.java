// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.adapter.persistence.project.ProjectRepositoryAdapter;
import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

/**
 * The test the storage design exists to satisfy.
 *
 * <p>The public ETag for a document is a hash of its stored bytes. If storing and reading back
 * changes those bytes by so much as a space, the ETag moves on every save even when the author
 * changed nothing — and every installed client re-downloads the whole catalogue on next launch.
 * Nothing looks broken. It just costs bandwidth and one-star reviews, weeks later, with nothing
 * obvious to connect them to.
 *
 * <p>So the document is deliberately written here with awkward but legal formatting: odd
 * whitespace, keys out of alphabetical order, an explicit {@code 1.0}. All the things a
 * deserialise-then-re-serialise round trip would quietly tidy up.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({ProjectRepositoryAdapter.class, WaveRepositoryAdapter.class})
class WaveRoundTripByteStabilityTest {

    private static final Instant NOW = Instant.parse("2026-08-30T09:00:00Z");

    /**
     * Not pretty-printed, not sorted, and carrying a float that is an integer. A normalising round
     * trip would produce something equivalent and different, which is exactly what must not happen.
     */
    private static final String AWKWARD_BUT_LEGAL =
            "{\"name\":\"Odd\",   \"id\":\"awkward\",\n"
                    + "  \"schema_version\": 1,\n"
                    + "\"duration\":1.0,   \"nested\":{\"z\":1,\"a\":[1,2,3]}}";

    @Autowired private ProjectRepository projects;
    @Autowired private WaveRepository waves;
    @Autowired private TestEntityManager entityManager;

    private ProjectId project;

    @BeforeEach
    void aProject() {
        project = projects.save(Project.create(new Slug("mine"), "Mine", NOW)).id();
        entityManager.flush();
        entityManager.clear();
    }

    private Wave store(String document) {
        Wave saved =
                waves.save(
                        Wave.draft(
                                project,
                                new Slug("awkward"),
                                "Odd",
                                0,
                                1,
                                "https://ludus.dev/schemas/wave/v1.json",
                                new ContentBody(document),
                                NOW));
        entityManager.flush();
        entityManager.clear();
        return saved;
    }

    @Test
    void the_bytes_that_come_back_are_the_bytes_that_went_in() {
        store(AWKWARD_BUT_LEGAL);

        String readBack = waves.find(project, new Slug("awkward")).orElseThrow().body().json();

        assertThat(readBack)
                .as("whitespace, key order and 1.0-versus-1 must all survive storage")
                .isEqualTo(AWKWARD_BUT_LEGAL);
    }

    @Test
    void storing_an_identical_document_again_does_not_move_the_hash() {
        store(AWKWARD_BUT_LEGAL);
        String first = ContentHashes.ofDocument(
                waves.find(project, new Slug("awkward")).orElseThrow().body());

        store(AWKWARD_BUT_LEGAL);
        String second = ContentHashes.ofDocument(
                waves.find(project, new Slug("awkward")).orElseThrow().body());

        assertThat(second)
                .as("re-saving an unchanged document must not invalidate every client's cache")
                .isEqualTo(first);
    }

    @Test
    void a_changed_document_does_move_the_hash() {
        store(AWKWARD_BUT_LEGAL);
        String before = ContentHashes.ofDocument(
                waves.find(project, new Slug("awkward")).orElseThrow().body());

        store(AWKWARD_BUT_LEGAL.replace("\"Odd\"", "\"Odder\""));
        String after = ContentHashes.ofDocument(
                waves.find(project, new Slug("awkward")).orElseThrow().body());

        assertThat(after).isNotEqualTo(before);
    }

    // The generated jsonb column is PostgreSQL-only and lives in postgresql/V4.1, so H2 never
    // creates it and there is nothing to assert here. CI checks it against the real database in
    // the Quickstart job, which is the only place a claim about PostgreSQL behaviour is worth
    // making. Asserting it here would mean asserting something about H2 and calling it PostgreSQL.
}
