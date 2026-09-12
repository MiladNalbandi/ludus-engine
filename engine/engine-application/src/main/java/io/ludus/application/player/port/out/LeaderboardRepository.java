// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.Leaderboard;
import io.ludus.domain.player.LeaderboardEntry;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** Boards, scores, and the ranking query. */
public interface LeaderboardRepository {

    Leaderboard save(Leaderboard board);

    Optional<Leaderboard> find(ProjectId projectId, Slug boardId);

    List<Leaderboard> list(ProjectId projectId);

    boolean delete(ProjectId projectId, Slug boardId);

    /**
     * Records a score, keeping the better of the two.
     *
     * <p>Better, not latest. A leaderboard that took the most recent score would drop a player's
     * best the moment they played a worse round, which is not what anybody means by a high-score
     * table — and the direction of "better" comes from the board rather than the caller.
     *
     * @return the score afterwards
     */
    long submit(ProjectId projectId, Slug boardId, PlayerId playerId, long score, Instant at);

    /**
     * A page of the board, in rank order.
     *
     * <p><b>Keyset, never offset.</b> Scores change constantly, so an offset re-counts rows that
     * have moved underneath it and pages skip and repeat entries. The cursor is the last row of the
     * previous page — its score <em>and</em> its player id, because scores tie constantly and a
     * cursor over a non-total order is not exact.
     */
    List<LeaderboardEntry> page(ProjectId projectId, Leaderboard board, Cursor after, int limit);

    /** Where a single player sits, or empty when they have no score on this board. */
    Optional<LeaderboardEntry> entryOf(ProjectId projectId, Leaderboard board, PlayerId playerId);

    long count(ProjectId projectId, Slug boardId);

    /** The last row of a page: both fields, because a score alone does not identify a row. */
    record Cursor(long score, PlayerId playerId) {}
}
