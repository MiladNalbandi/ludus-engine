// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;

import io.ludus.application.content.port.out.DocumentReader;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.content.WaveOrderPolicy;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class AuthorWaveTest {

    private static final Instant NOW = Instant.parse("2026-08-30T09:00:00Z");
    private static final ProjectId PROJECT = ProjectId.random();
    private static final ProjectId OTHER = ProjectId.random();
    private static final ContentBody BODY = new ContentBody("{\"id\":\"boss_rush\"}");

    private final ContentFakes.Waves waves = new ContentFakes.Waves();
    private final ContentFakes.Validator validator = new ContentFakes.Validator();
    private final ContentFakes.Reader reader = new ContentFakes.Reader();
    private final ContentFakes.Stamper stamper = new ContentFakes.Stamper();

    private final AuthorWave author =
            new AuthorWave(waves, validator, reader, stamper, 1, Clock.fixed(NOW, ZoneOffset.UTC));

    @BeforeEach
    void aValidDocument() {
        reader.nextResult =
                new DocumentReader.IndexedFields("boss_rush", "Boss Rush", 3, Optional.of(1));
    }

    @Test
    void a_valid_document_is_stored_as_a_draft() {
        Wave saved = author.author(PROJECT, Optional.empty(), BODY);

        assertThat(saved.id()).isEqualTo(new Slug("boss_rush"));
        assertThat(saved.name()).isEqualTo("Boss Rush");
        assertThat(saved.order()).isEqualTo(3);
        assertThat(saved.body()).isEqualTo(BODY);
        assertThat(saved.published())
                .as("saving must never publish; a half-finished level is not a release")
                .isFalse();
    }

    @Test
    void an_invalid_document_is_rejected_with_every_violation_at_once() {
        validator.nextResult =
                List.of(
                        new ContentViolation("/constraints/time_limit", "is required"),
                        new ContentViolation("/spawn_rules", "must contain at least 1 item"));

        assertThatExceptionOfType(ContentRejected.class)
                .isThrownBy(() -> author.author(PROJECT, Optional.empty(), BODY))
                .satisfies(
                        rejection ->
                                assertThat(rejection.violations())
                                        .as("fixing one field at a time is the slowest way to"
                                                + " correct a document")
                                        .hasSize(2));

        assertThat(waves.list(PROJECT)).isEmpty();
    }

    /**
     * Stamping happens before validation, so the document that gets checked is the document that
     * gets stored. Validate first and the stamp could introduce something the schema forbids, with
     * nothing left to catch it.
     */
    @Test
    void the_stamped_body_is_the_one_that_is_stored() {
        stamper.alreadyVersioned = false;

        Wave saved = author.author(PROJECT, Optional.empty(), BODY);

        assertThat(stamper.stampCalls).isEqualTo(1);
        assertThat(saved.body().json()).isEqualTo(BODY.json() + "/*stamped:1*/");
    }

    @Test
    void a_second_wave_may_not_claim_an_order_that_is_taken() {
        author.author(PROJECT, Optional.empty(), BODY);
        reader.nextResult =
                new DocumentReader.IndexedFields("other_wave", "Other", 3, Optional.of(1));

        assertThatExceptionOfType(ContentRejected.class)
                .isThrownBy(() -> author.author(PROJECT, Optional.empty(), BODY))
                .satisfies(
                        rejection ->
                                assertThat(rejection.violations())
                                        .singleElement()
                                        .satisfies(
                                                violation -> {
                                                    assertThat(violation.pointer())
                                                            .isEqualTo(
                                                                    WaveOrderPolicy.ORDER_POINTER);
                                                    assertThat(violation.message())
                                                            .contains("already taken");
                                                }));
    }

    /** Re-saving a wave unchanged must not be a collision with itself. */
    @Test
    void a_wave_may_keep_its_own_order_when_it_is_updated() {
        author.author(PROJECT, Optional.empty(), BODY);

        Wave again = author.author(PROJECT, Optional.of(new Slug("boss_rush")), BODY);

        assertThat(again.order()).isEqualTo(3);
        assertThat(waves.list(PROJECT)).hasSize(1);
    }

    /** Orders are per project. Two projects may each have a wave at order 3. */
    @Test
    void another_projects_order_is_not_a_collision() {
        author.author(OTHER, Optional.empty(), BODY);

        assertThat(author.author(PROJECT, Optional.empty(), BODY).order()).isEqualTo(3);
    }

    @Test
    void the_url_and_the_document_must_agree_about_the_id() {
        assertThatExceptionOfType(ContentRejected.class)
                .isThrownBy(() -> author.author(PROJECT, Optional.of(new Slug("something_else")), BODY))
                .satisfies(
                        rejection ->
                                assertThat(rejection.violations())
                                        .singleElement()
                                        .satisfies(v -> assertThat(v.pointer()).isEqualTo("/id")));
    }

    @Test
    void updating_a_wave_keeps_its_publication_state_and_creation_time() {
        Wave created = author.author(PROJECT, Optional.empty(), BODY);
        waves.save(created.published(true, NOW));

        reader.nextResult =
                new DocumentReader.IndexedFields("boss_rush", "Renamed", 3, Optional.of(1));
        Wave updated = author.author(PROJECT, Optional.of(new Slug("boss_rush")), BODY);

        assertThat(updated.published())
                .as("an edit is not an unpublish; withdrawing content is a separate decision")
                .isTrue();
        assertThat(updated.name()).isEqualTo("Renamed");
        assertThat(updated.createdAt()).isEqualTo(created.createdAt());
    }

    @Test
    void a_document_whose_id_is_not_a_slug_is_rejected_at_that_field() {
        reader.nextResult =
                new DocumentReader.IndexedFields("Not A Slug", "Bad", 0, Optional.of(1));

        assertThatExceptionOfType(ContentRejected.class)
                .isThrownBy(() -> author.author(PROJECT, Optional.empty(), BODY))
                .satisfies(
                        rejection ->
                                assertThat(rejection.violations())
                                        .singleElement()
                                        .satisfies(v -> assertThat(v.pointer()).isEqualTo("/id")));
    }
}
