// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.DocumentReader;
import io.ludus.application.content.port.out.DocumentValidator;
import io.ludus.application.content.port.out.SchemaVersionStamper;
import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.content.WaveOrderPolicy;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Creating and replacing a wave document.
 *
 * <p>The order of operations is the interesting part, and it is fixed: stamp, then validate, then
 * read, then store. Stamping first means the document that gets validated is the document that gets
 * stored — validate first and the stamp could introduce something the schema forbids, with nothing
 * left to catch it. Reading after validating means the extraction can assume the shape it needs is
 * present, instead of defending against every absence twice.
 *
 * <p>Saving never publishes. A wave arrives as a draft and stays one until somebody says otherwise,
 * because the alternative is that saving a half-finished level ships it to everyone currently
 * playing.
 */
public class AuthorWave {

    private final WaveRepository waves;
    private final DocumentValidator validator;
    private final DocumentReader reader;
    private final SchemaVersionStamper stamper;
    private final int currentSchemaVersion;
    private final Clock clock;

    public AuthorWave(
            WaveRepository waves,
            DocumentValidator validator,
            DocumentReader reader,
            SchemaVersionStamper stamper,
            int currentSchemaVersion,
            Clock clock) {
        this.waves = waves;
        this.validator = validator;
        this.reader = reader;
        this.stamper = stamper;
        this.currentSchemaVersion = currentSchemaVersion;
        this.clock = clock;
    }

    /**
     * Creates a wave, or replaces the document of one that exists.
     *
     * @param requestedId the id from the URL, or empty on create — where it is supplied it must
     *     agree with the document, because two ids for one thing is a question nobody should have
     *     to answer
     * @throws ContentRejected with every violation found, at JSON Pointer paths
     */
    public Wave author(ProjectId projectId, Optional<Slug> requestedId, ContentBody submitted) {
        ContentBody body = stamper.stampIfAbsent(submitted, currentSchemaVersion);

        List<ContentViolation> violations = new ArrayList<>(validator.validate(body));
        if (!violations.isEmpty()) {
            throw new ContentRejected(violations);
        }

        DocumentReader.IndexedFields fields = reader.read(body);
        Slug id = parseId(fields.id());
        requestedId.ifPresent(
                fromUrl -> {
                    if (!fromUrl.equals(id)) {
                        throw new ContentRejected(
                                List.of(
                                        new ContentViolation(
                                                "/id",
                                                "the document says '"
                                                        + id.value()
                                                        + "' but the URL says '"
                                                        + fromUrl.value()
                                                        + "'")));
                    }
                });

        // Excluding this wave's own order, so re-saving a document unchanged is not a collision
        // with itself. The unique index is what makes this safe under concurrency; this check
        // exists so the author gets a message pointing at the field rather than a constraint name.
        WaveOrderPolicy.collision(fields.order(), waves.takenOrders(projectId, id))
                .ifPresent(
                        taken -> {
                            throw new ContentRejected(
                                    List.of(
                                            new ContentViolation(
                                                    WaveOrderPolicy.ORDER_POINTER,
                                                    "order " + taken + " is already taken by "
                                                            + "another wave in this project")));
                        });

        Instant now = clock.instant();
        int schemaVersion = fields.schemaVersion().orElse(currentSchemaVersion);

        return waves.save(
                waves.find(projectId, id)
                        .map(existing ->
                                existing.withBody(
                                        fields.name(), fields.order(), schemaVersion, body, now))
                        .orElseGet(() ->
                                Wave.draft(
                                        projectId,
                                        id,
                                        fields.name(),
                                        fields.order(),
                                        schemaVersion,
                                        validator.schemaUri(),
                                        body,
                                        now)));
    }

    private Slug parseId(String value) {
        try {
            return new Slug(value);
        } catch (IllegalArgumentException malformed) {
            // The schema's own pattern should have caught this first. If it did not, the schema and
            // the domain disagree about what an id is, which is worth saying plainly.
            throw new ContentRejected(
                    List.of(new ContentViolation("/id", malformed.getMessage())));
        }
    }
}
