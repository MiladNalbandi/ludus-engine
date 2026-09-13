// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.port.out.LeaderboardRepository;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.domain.player.Leaderboard;
import io.ludus.domain.player.LeaderboardEntry;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.util.List;
import java.util.Optional;

/**
 * Boards, scores and ranks.
 *
 * <p><b>A player may submit their own score.</b> Unlike currency, which only an editor can grant:
 * the asymmetry is the same trust model applied honestly. A forged score is cheating, and a
 * client-authoritative leaderboard can always be cheated — the engine cannot tell a real lap time
 * from an invented one, and no amount of credential design changes that. Pretending otherwise by
 * requiring a server credential would stop the games that have no server and inconvenience nobody
 * else.
 *
 * <p>So the honest position is stated rather than implied: <em>a leaderboard fed by clients is a
 * leaderboard of what clients claimed</em>. A game that needs better than that submits scores from
 * its own server with an editor credential, which this also allows.
 */
public class Leaderboards {

    /** A page size cap. One request should not be able to ask for the whole board. */
    public static final int MAX_PAGE = 200;

    private final LeaderboardRepository boards;
    private final PlayerRepository players;
    private final Clock clock;

    public Leaderboards(LeaderboardRepository boards, PlayerRepository players, Clock clock) {
        this.boards = boards;
        this.players = players;
        this.clock = clock;
    }

    public List<Leaderboard> list(ProjectId projectId) {
        return boards.list(projectId);
    }

    public Optional<Leaderboard> find(ProjectId projectId, Slug boardId) {
        return boards.find(projectId, boardId);
    }

    public Leaderboard save(ProjectId projectId, Slug boardId, String name, boolean descending) {
        if (name == null || name.isBlank()) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/name", "a leaderboard needs a name")));
        }
        return boards.save(
                boards.find(projectId, boardId)
                        .map(existing -> existing.with(name, descending, clock.instant()))
                        .orElseGet(
                                () ->
                                        Leaderboard.create(
                                                projectId, boardId, name, descending, clock.instant())));
    }

    public boolean delete(ProjectId projectId, Slug boardId) {
        return boards.delete(projectId, boardId);
    }

    /**
     * Records a score, keeping the better of the two.
     *
     * @return the score the board now holds for this player, which may be the one it already had
     */
    public long submit(ProjectId projectId, Slug boardId, PlayerId playerId, long score) {
        boards.find(projectId, boardId)
                .orElseThrow(
                        () ->
                                new ContentRejected(
                                        List.of(
                                                ContentViolation.atRoot(
                                                        "no leaderboard '" + boardId + "' in this project"))));
        if (players.find(projectId, playerId).isEmpty()) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("no such player in this project")));
        }
        return boards.submit(projectId, boardId, playerId, score, clock.instant());
    }

    /**
     * A page of a board.
     *
     * <p>What "stable" means here is worth stating precisely, because the alternative is implying
     * more than is true. Paging is keyset, so <b>a row whose score does not change is returned
     * exactly once across the whole walk</b> — never skipped, never repeated — however many other
     * scores are written while you page. A row whose score <em>does</em> change moves, and may be
     * seen twice or not at all; that is not a flaw to be fixed but what a live ranking is. An
     * offset-paged board gives neither guarantee.
     */
    public Page page(ProjectId projectId, Slug boardId, LeaderboardRepository.Cursor after, int limit) {
        Leaderboard board =
                boards.find(projectId, boardId)
                        .orElseThrow(
                                () ->
                                        new ContentRejected(
                                                List.of(
                                                        ContentViolation.atRoot(
                                                                "no leaderboard '" + boardId + "'"))));

        int size = Math.max(1, Math.min(MAX_PAGE, limit));
        // One more than asked for, so "is there another page" needs no second query.
        List<LeaderboardEntry> found = boards.page(projectId, board, after, size + 1);
        boolean more = found.size() > size;
        List<LeaderboardEntry> entries = more ? found.subList(0, size) : found;

        return new Page(
                board,
                entries,
                boards.count(projectId, boardId),
                more && !entries.isEmpty()
                        ? new LeaderboardRepository.Cursor(
                                entries.get(entries.size() - 1).score(),
                                entries.get(entries.size() - 1).playerId())
                        : null);
    }

    /** Where one player sits, or empty when they have not scored on this board. */
    public Optional<LeaderboardEntry> entryOf(ProjectId projectId, Slug boardId, PlayerId playerId) {
        return boards.find(projectId, boardId)
                .flatMap(board -> boards.entryOf(projectId, board, playerId));
    }

    /** A page, and where to continue. {@code next} is null at the end. */
    public record Page(
            Leaderboard board,
            List<LeaderboardEntry> entries,
            long total,
            LeaderboardRepository.Cursor next) {}
}
