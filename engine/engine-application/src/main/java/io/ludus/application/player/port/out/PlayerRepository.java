// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;

/** Storage for players. Project-scoped, like every repository here. */
public interface PlayerRepository {

    Player save(Player player);

    Optional<Player> find(ProjectId projectId, PlayerId id);

    /** By the game's own identifier, which is what a client presents. */
    Optional<Player> findByExternalId(ProjectId projectId, String externalId);

    /**
     * A page of players, most recently seen first.
     *
     * <p>Keyset paging rather than an offset: an offset re-counts rows on every page and skips or
     * repeats entries when the ordering column changes underneath it — and {@code last_seen_at}
     * changes on every session, which is exactly the unstable case. The cursor is the last row of
     * the previous page.
     */
    List<Player> page(ProjectId projectId, PlayerPageCursor after, int limit);

    long count(ProjectId projectId);

    /** Where the previous page stopped. Both fields, because timestamps are not unique. */
    record PlayerPageCursor(java.time.Instant lastSeenAt, PlayerId id) {}
}
