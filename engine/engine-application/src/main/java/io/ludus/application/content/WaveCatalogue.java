// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.Wave;
import io.ludus.domain.content.WaveOrderPolicy;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.util.List;
import java.util.Optional;

/**
 * Reading, publishing and removing waves.
 *
 * <p>Two views of the same table, and keeping them apart is the point. {@link #forAuthors} shows
 * everything including drafts; {@link #published} shows only what has been published, and is what
 * will eventually back the public routes. An unpublished wave is not merely hidden from a client —
 * to a client it does not exist, and the difference between "hidden" and "does not exist" is the
 * difference between {@code 403} and {@code 404}.
 */
public class WaveCatalogue {

    private final WaveRepository waves;
    private final Clock clock;

    public WaveCatalogue(WaveRepository waves, Clock clock) {
        this.waves = waves;
        this.clock = clock;
    }

    public List<Wave> forAuthors(ProjectId projectId) {
        return waves.list(projectId);
    }

    public List<Wave> published(ProjectId projectId) {
        return waves.listPublished(projectId);
    }

    public Optional<Wave> find(ProjectId projectId, Slug id) {
        return waves.find(projectId, id);
    }

    /** The hash behind both the poll and the list ETag. See {@link ContentHashes}. */
    public String publishedContentHash(ProjectId projectId) {
        return ContentHashes.ofCatalogue(waves.publishedCatalogue(projectId));
    }

    /** What order a new wave could take without colliding. Advisory; the document decides. */
    public int suggestNextOrder(ProjectId projectId) {
        return WaveOrderPolicy.suggestNext(waves.takenOrders(projectId, null));
    }

    /** @return the wave in its new state, or empty if there is no such wave in this project */
    public Optional<Wave> setPublished(ProjectId projectId, Slug id, boolean published) {
        return waves.find(projectId, id)
                .map(wave -> waves.save(wave.published(published, clock.instant())));
    }

    public boolean delete(ProjectId projectId, Slug id) {
        return waves.delete(projectId, id);
    }
}
