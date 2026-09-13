// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.LeaderboardRepository;
import io.ludus.domain.player.Leaderboard;
import io.ludus.domain.player.LeaderboardEntry;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/**
 * Boards and the ranking query.
 *
 * <p>The interesting part is {@link #page}: a keyset walk over {@code (score, player_id)}, in the
 * board's direction. The tie-break is not decoration — scores tie constantly, and a cursor over an
 * order that is not total will skip and repeat rows at every tie.
 */
@Repository
public class LeaderboardRepositoryAdapter implements LeaderboardRepository {

    private final JdbcClient jdbc;

    LeaderboardRepositoryAdapter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional
    public Leaderboard save(Leaderboard board) {
        java.sql.Timestamp updated = java.sql.Timestamp.from(board.updatedAt().truncatedTo(ChronoUnit.MICROS));
        int changed =
                jdbc.sql(
                                """
                                update leaderboard
                                   set name = :name, descending = :descending, updated_at = :updatedAt
                                 where project_id = :projectId and board_id = :boardId
                                """)
                        .param("name", board.name())
                        .param("descending", board.descending())
                        .param("updatedAt", updated)
                        .param("projectId", board.projectId().value())
                        .param("boardId", board.id().value())
                        .update();

        if (changed == 0) {
            jdbc.sql(
                            """
                            insert into leaderboard
                                   (project_id, board_id, name, descending, created_at, updated_at)
                            values (:projectId, :boardId, :name, :descending, :createdAt, :updatedAt)
                            """)
                    .param("projectId", board.projectId().value())
                    .param("boardId", board.id().value())
                    .param("name", board.name())
                    .param("descending", board.descending())
                    .param("createdAt", java.sql.Timestamp.from(board.createdAt().truncatedTo(ChronoUnit.MICROS)))
                    .param("updatedAt", updated)
                    .update();
        }
        return find(board.projectId(), board.id()).orElseThrow();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Leaderboard> find(ProjectId projectId, Slug boardId) {
        return jdbc.sql(
                        """
                        select project_id, board_id, name, descending, created_at, updated_at
                          from leaderboard
                         where project_id = :projectId and board_id = :boardId
                        """)
                .param("projectId", projectId.value())
                .param("boardId", boardId.value())
                .query((rs, row) -> toBoard(rs))
                .optional();
    }

    @Override
    @Transactional(readOnly = true)
    public List<Leaderboard> list(ProjectId projectId) {
        return jdbc.sql(
                        """
                        select project_id, board_id, name, descending, created_at, updated_at
                          from leaderboard where project_id = :projectId order by board_id
                        """)
                .param("projectId", projectId.value())
                .query((rs, row) -> toBoard(rs))
                .list();
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, Slug boardId) {
        return jdbc.sql("delete from leaderboard where project_id = :projectId and board_id = :boardId")
                        .param("projectId", projectId.value())
                        .param("boardId", boardId.value())
                        .update()
                > 0;
    }

    /**
     * Keeps the better score, decided in the database.
     *
     * <p>The comparison is in the {@code where} clause, so the read and the write are one
     * operation. Read-then-compare-then-write loses a better score that arrived in between — twice
     * as likely here as anywhere, because a leaderboard is written by everybody at once at the end
     * of a round.
     */
    @Override
    @Transactional
    public long submit(ProjectId projectId, Slug boardId, PlayerId playerId, long score, Instant at) {
        java.sql.Timestamp when = java.sql.Timestamp.from(at.truncatedTo(ChronoUnit.MICROS));
        boolean descending = find(projectId, boardId).map(Leaderboard::descending).orElse(true);

        int updated =
                jdbc.sql(
                                descending
                                        ? """
                                          update leaderboard_entry set score = :score, updated_at = :at
                                           where project_id = :projectId and board_id = :boardId
                                             and player_id = :playerId and score < :score
                                          """
                                        : """
                                          update leaderboard_entry set score = :score, updated_at = :at
                                           where project_id = :projectId and board_id = :boardId
                                             and player_id = :playerId and score > :score
                                          """)
                        .param("score", score)
                        .param("at", when)
                        .param("projectId", projectId.value())
                        .param("boardId", boardId.value())
                        .param("playerId", playerId.value())
                        .update();

        if (updated == 0) {
            try {
                jdbc.sql(
                                """
                                insert into leaderboard_entry
                                       (project_id, board_id, player_id, score, updated_at)
                                values (:projectId, :boardId, :playerId, :score, :at)
                                """)
                        .param("projectId", projectId.value())
                        .param("boardId", boardId.value())
                        .param("playerId", playerId.value())
                        .param("score", score)
                        .param("at", when)
                        .update();
            } catch (DataIntegrityViolationException existing) {
                // The row was already there with a score at least as good -- the update matched
                // nothing because the existing score wins, not because the row was missing. Or
                // another thread inserted first. Either way the board already holds the better one.
            }
        }
        return scoreOf(projectId, boardId, playerId).orElse(score);
    }

    @Override
    @Transactional(readOnly = true)
    public List<LeaderboardEntry> page(
            ProjectId projectId, Leaderboard board, Cursor after, int limit) {

        String comparison =
                board.descending()
                        ? "(e.score < :score or (e.score = :score and e.player_id < :playerId))"
                        : "(e.score > :score or (e.score = :score and e.player_id > :playerId))";
        String order =
                board.descending()
                        ? "order by e.score desc, e.player_id desc"
                        : "order by e.score asc, e.player_id asc";

        String sql =
                """
                select e.player_id, e.score, e.updated_at, p.display_name
                  from leaderboard_entry e
                  join player p on p.id = e.player_id
                 where e.project_id = :projectId and e.board_id = :boardId
                """
                        + (after == null ? "" : " and " + comparison + "\n")
                        + " "
                        + order;

        var query =
                jdbc.sql(sql)
                        .param("projectId", projectId.value())
                        .param("boardId", board.id().value());
        if (after != null) {
            query = query.param("score", after.score()).param("playerId", after.playerId().value());
        }

        List<LeaderboardEntry> rows =
                query.query(
                                (rs, row) ->
                                        new Object[] {
                                            new PlayerId((UUID) rs.getObject("player_id")),
                                            rs.getString("display_name"),
                                            rs.getLong("score"),
                                            rs.getTimestamp("updated_at").toInstant()
                                        })
                        .list()
                        .stream()
                        .limit(limit)
                        .map(
                                columns ->
                                        new LeaderboardEntry(
                                                (PlayerId) columns[0],
                                                (String) columns[1],
                                                (Long) columns[2],
                                                // Filled in below: rank depends on where the page
                                                // starts, which the query does not know.
                                                1,
                                                (Instant) columns[3]))
                        .toList();

        if (rows.isEmpty()) {
            return rows;
        }

        // The rank of the first row of this page, counted once rather than per row.
        long firstRank = after == null ? 1 : rankOf(projectId, board, rows.get(0).score(), rows.get(0).playerId());
        List<LeaderboardEntry> ranked = new java.util.ArrayList<>(rows.size());
        for (int index = 0; index < rows.size(); index++) {
            LeaderboardEntry row = rows.get(index);
            ranked.add(
                    new LeaderboardEntry(
                            row.playerId(), row.displayName(), row.score(), firstRank + index, row.updatedAt()));
        }
        return List.copyOf(ranked);
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<LeaderboardEntry> entryOf(ProjectId projectId, Leaderboard board, PlayerId playerId) {
        return jdbc.sql(
                        """
                        select e.player_id, e.score, e.updated_at, p.display_name
                          from leaderboard_entry e
                          join player p on p.id = e.player_id
                         where e.project_id = :projectId and e.board_id = :boardId
                           and e.player_id = :playerId
                        """)
                .param("projectId", projectId.value())
                .param("boardId", board.id().value())
                .param("playerId", playerId.value())
                .query(
                        (rs, row) ->
                                new LeaderboardEntry(
                                        new PlayerId((UUID) rs.getObject("player_id")),
                                        rs.getString("display_name"),
                                        rs.getLong("score"),
                                        1,
                                        rs.getTimestamp("updated_at").toInstant()))
                .optional()
                .map(
                        entry ->
                                new LeaderboardEntry(
                                        entry.playerId(),
                                        entry.displayName(),
                                        entry.score(),
                                        rankOf(projectId, board, entry.score(), entry.playerId()),
                                        entry.updatedAt()));
    }

    /** How many rows sort strictly before this one, plus one. */
    private long rankOf(ProjectId projectId, Leaderboard board, long score, PlayerId playerId) {
        String ahead =
                board.descending()
                        ? "(score > :score or (score = :score and player_id > :playerId))"
                        : "(score < :score or (score = :score and player_id < :playerId))";
        return jdbc.sql(
                        "select count(*) from leaderboard_entry"
                                + " where project_id = :projectId and board_id = :boardId and "
                                + ahead)
                .param("projectId", projectId.value())
                .param("boardId", board.id().value())
                .param("score", score)
                .param("playerId", playerId.value())
                .query(Long.class)
                .single()
                + 1;
    }

    @Override
    @Transactional(readOnly = true)
    public long count(ProjectId projectId, Slug boardId) {
        return jdbc.sql(
                        "select count(*) from leaderboard_entry"
                                + " where project_id = :projectId and board_id = :boardId")
                .param("projectId", projectId.value())
                .param("boardId", boardId.value())
                .query(Long.class)
                .single();
    }

    private Optional<Long> scoreOf(ProjectId projectId, Slug boardId, PlayerId playerId) {
        return jdbc.sql(
                        """
                        select score from leaderboard_entry
                         where project_id = :projectId and board_id = :boardId and player_id = :playerId
                        """)
                .param("projectId", projectId.value())
                .param("boardId", boardId.value())
                .param("playerId", playerId.value())
                .query(Long.class)
                .optional();
    }

    private static Leaderboard toBoard(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new Leaderboard(
                new ProjectId((UUID) rs.getObject("project_id")),
                new Slug(rs.getString("board_id")),
                rs.getString("name"),
                rs.getBoolean("descending"),
                rs.getTimestamp("created_at").toInstant(),
                rs.getTimestamp("updated_at").toInstant());
    }
}
