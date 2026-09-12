// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.Leaderboards;
import io.ludus.domain.player.Leaderboard;
import io.ludus.domain.player.LeaderboardEntry;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

final class LeaderboardDtos {

    private LeaderboardDtos() {}

    @Schema(name = "LeaderboardView", description = "A board the project defines, and which way it sorts.")
    record BoardView(String id, String name, boolean descending, Instant createdAt, Instant updatedAt) {

        static BoardView of(Leaderboard board) {
            return new BoardView(
                    board.id().value(), board.name(), board.descending(), board.createdAt(), board.updatedAt());
        }
    }

    @Schema(name = "LeaderboardRequest", description = "A board to create or replace.")
    record BoardRequest(String name, Boolean descending) {}

    @Schema(name = "LeaderboardEntryView", description = "One player's place. Rank is computed, not stored.")
    record EntryView(String playerId, String displayName, long score, long rank, Instant updatedAt) {

        static EntryView of(LeaderboardEntry entry) {
            return new EntryView(
                    entry.playerId().toString(),
                    entry.displayName(),
                    entry.score(),
                    entry.rank(),
                    entry.updatedAt());
        }
    }

    /**
     * A page of a board.
     *
     * <p>{@code nextCursor} is opaque and is the only supported way to ask for the next page. There
     * is deliberately no page number: scores change constantly, so an offset would skip and repeat
     * entries as people play.
     */
    @Schema(name = "LeaderboardPage", description = "A page of a board, with the cursor for the next.")
    record PageView(BoardView board, List<EntryView> entries, long total, String nextCursor) {

        static PageView of(Leaderboards.Page page) {
            return new PageView(
                    BoardView.of(page.board()),
                    page.entries().stream().map(EntryView::of).toList(),
                    page.total(),
                    page.next() == null
                            ? null
                            : page.next().score() + ":" + page.next().playerId());
        }
    }

    @Schema(name = "ScoreSubmission", description = "A score to record. The better of the two is kept.")
    record ScoreRequest(Long score) {}
}
