// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.util.List;
import java.util.Optional;

/** Storage for waves. Every method is scoped to a project, like every repository here. */
public interface WaveRepository {

    Optional<Wave> find(ProjectId projectId, Slug id);

    /** Every wave in the project, drafts included. The authoring view. */
    List<Wave> list(ProjectId projectId);

    /** Only what has been published. What a game client is served. */
    List<Wave> listPublished(ProjectId projectId);

    /**
     * One published wave, or empty.
     *
     * <p>Separate from {@link #find} rather than a filter applied afterwards, so that "which rows
     * may a client see" is answered by the query rather than by whoever remembers to check. A
     * caller holding this method cannot accidentally serve a draft.
     */
    Optional<Wave> findPublished(ProjectId projectId, Slug id);

    Wave save(Wave wave);

    boolean delete(ProjectId projectId, Slug id);

    /**
     * The orders currently taken, excluding one wave.
     *
     * <p>The exclusion is what lets an update keep its own order without colliding with itself,
     * and doing it in the query rather than by filtering afterwards keeps that correct when the
     * list is long.
     */
    List<Integer> takenOrders(ProjectId projectId, Slug excluding);

    /**
     * Id and last-modified for every published wave — the input to the catalogue hash.
     *
     * <p>Its own method rather than mapping over {@link #listPublished}, because this is called on
     * every client poll and has no business loading a document body to answer.
     */
    List<ContentHashes.Entry> publishedCatalogue(ProjectId projectId);
}
