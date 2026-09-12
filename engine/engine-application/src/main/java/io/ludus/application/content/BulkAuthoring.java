// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.UnitOfWork;
import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Importing or removing many waves at once, all or nothing.
 *
 * <p>All or nothing is the requirement, not a nicety. A partially applied import leaves an author
 * with two problems they cannot solve from the response: which documents landed, and whether
 * retrying will duplicate the ones that did. Every wave here shares one transaction, so the answer
 * is always "all of them" or "none of them".
 *
 * <p>Violations are reported with the index of the document that caused them prefixed onto the
 * pointer — {@code /3/progression_config/order} rather than {@code /progression_config/order} —
 * because thirty documents in and "the order collides" names nothing an editor can open.
 */
public class BulkAuthoring {

    /**
     * A ceiling on one request, so that a batch cannot become an accidental denial of service.
     *
     * <p>Fifty is well above any real import — the demo set is three, and a large game's catalogue
     * is tens — and low enough that the whole batch is a reasonable amount of work to hold in one
     * transaction. A caller with more sends more requests, which is also what makes progress
     * visible to whoever is watching an import run.
     */
    public static final int MAX_BATCH = 50;

    private final AuthorWave authorWave;
    private final WaveRepository waves;
    private final UnitOfWork unitOfWork;

    public BulkAuthoring(AuthorWave authorWave, WaveRepository waves, UnitOfWork unitOfWork) {
        this.authorWave = authorWave;
        this.waves = waves;
        this.unitOfWork = unitOfWork;
    }

    /**
     * Creates or replaces every document, or none of them.
     *
     * <p>Each document goes through {@link AuthorWave}, so nothing here is a second, laxer write
     * path: the same stamping, the same schema validation, the same derived order and the same
     * collision check apply. That matters more than the saved keystrokes — a bulk endpoint that
     * validated differently from the single one would be the way invalid content got in.
     */
    public List<Wave> importAll(ProjectId projectId, List<ContentBody> documents) {
        requireSane(documents, "documents");

        return unitOfWork.inOne(
                () -> {
                    List<Wave> saved = new ArrayList<>();
                    List<ContentViolation> violations = new ArrayList<>();

                    for (int index = 0; index < documents.size(); index++) {
                        try {
                            saved.add(
                                    authorWave.author(
                                            projectId, Optional.empty(), documents.get(index)));
                        } catch (ContentRejected rejected) {
                            violations.addAll(at(index, rejected.violations()));
                        }
                    }

                    if (!violations.isEmpty()) {
                        // Rolls back everything above. Thrown after the whole batch rather than at
                        // the first failure, so one request reports every bad document instead of
                        // one per round trip.
                        throw new ContentRejected(violations);
                    }
                    return List.copyOf(saved);
                });
    }

    /**
     * Deletes every named wave, or none of them.
     *
     * <p>An id that is not there is a violation rather than a silent skip. "Delete these six" is a
     * statement about a known set, and a caller who sent a typo has a different catalogue than they
     * think they do — which is worth finding out now rather than from the five that did go.
     */
    public int deleteAll(ProjectId projectId, List<String> ids) {
        requireSane(ids, "ids");

        return unitOfWork.inOne(
                () -> {
                    List<ContentViolation> violations = new ArrayList<>();
                    int deleted = 0;

                    for (int index = 0; index < ids.size(); index++) {
                        String candidate = ids.get(index);
                        if (candidate == null || !Slug.isValid(candidate)) {
                            violations.add(
                                    new ContentViolation(
                                            "/" + index, "'" + candidate + "' is not a wave id"));
                            continue;
                        }
                        if (waves.delete(projectId, new Slug(candidate))) {
                            deleted++;
                        } else {
                            violations.add(
                                    new ContentViolation(
                                            "/" + index,
                                            "no wave '" + candidate + "' in this project"));
                        }
                    }

                    if (!violations.isEmpty()) {
                        throw new ContentRejected(violations);
                    }
                    return deleted;
                });
    }

    private void requireSane(List<?> items, String what) {
        if (items == null || items.isEmpty()) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("send at least one of " + what)));
        }
        if (items.size() > MAX_BATCH) {
            throw new ContentRejected(
                    List.of(
                            ContentViolation.atRoot(
                                    "at most " + MAX_BATCH + " per request, received "
                                            + items.size())));
        }
    }

    /** Re-points a violation at the document that produced it, within the batch. */
    private List<ContentViolation> at(int index, List<ContentViolation> violations) {
        return violations.stream()
                .map(v -> new ContentViolation("/" + index + v.pointer(), v.message()))
                .toList();
    }
}
