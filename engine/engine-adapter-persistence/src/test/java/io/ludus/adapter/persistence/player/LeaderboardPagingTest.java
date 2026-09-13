// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.adapter.persistence.project.ProjectRepositoryAdapter;
import io.ludus.application.player.port.out.LeaderboardRepository;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.player.Leaderboard;
import io.ludus.domain.player.LeaderboardEntry;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * The acceptance criterion: paging stable under concurrent writes.
 *
 * <p>What that can mean is worth being precise about, because the obvious phrasing promises more
 * than any live ranking can deliver. Keyset paging guarantees exactly this: <b>a row whose score
 * does not change is returned exactly once across the whole walk</b> — never skipped, never
 * repeated — however many other scores are written while you page. A row whose score does change
 * moves, and may be seen twice or not at all. That is what a live ranking is, not a defect.
 *
 * <p>Offset paging guarantees neither, which is what {@link #walking_while_scores_change} would
 * demonstrate if the adapter used one.
 *
 * <p>Its own database and no rollback, for the reason spelled out in {@link WalletConcurrencyTest}:
 * these tests commit, and committed rows must not leak into other tests in this module.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@TestPropertySource(
        properties =
                "spring.datasource.url="
                        + "jdbc:h2:mem:ludus-leaderboard-paging"
                        + ";DB_CLOSE_DELAY=-1;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE")
@Import({
    ProjectRepositoryAdapter.class,
    PlayerRepositoryAdapter.class,
    LeaderboardRepositoryAdapter.class
})
class LeaderboardPagingTest {

    private static final Instant NOW = Instant.parse("2026-09-12T16:00:00Z");

    @Autowired private ProjectRepository projects;
    @Autowired private PlayerRepository players;
    @Autowired private LeaderboardRepository boards;

    private ProjectId project;
    private Slug boardId;
    private Leaderboard board;
    private final List<PlayerId> everyone = new ArrayList<>();

    private static String unique(String prefix) {
        return prefix + "_" + Long.toString(System.nanoTime(), 36);
    }

    @BeforeEach
    void aBoardWithScores() {
        project = projects.save(Project.create(new Slug(unique("p")), "Project", NOW)).id();
        boardId = new Slug(unique("board"));
        board = boards.save(Leaderboard.create(project, boardId, "High scores", true, NOW));
        everyone.clear();
    }

    private PlayerId scorer(String name, long score) {
        PlayerId id =
                players.save(Player.firstSeen(PlayerId.random(), project, unique("device"), NOW).named(name, NOW))
                        .id();
        boards.submit(project, boardId, id, score, NOW);
        everyone.add(id);
        return id;
    }

    private List<LeaderboardEntry> walk(int pageSize, Runnable between) {
        List<LeaderboardEntry> seen = new ArrayList<>();
        LeaderboardRepository.Cursor cursor = null;
        // A bound, so a paging bug that never terminates fails as a test rather than hanging CI.
        for (int page = 0; page < 100; page++) {
            List<LeaderboardEntry> rows = boards.page(project, board, cursor, pageSize);
            if (rows.isEmpty()) {
                break;
            }
            seen.addAll(rows);
            LeaderboardEntry last = rows.get(rows.size() - 1);
            cursor = new LeaderboardRepository.Cursor(last.score(), last.playerId());
            between.run();
        }
        return seen;
    }

    @Test
    void a_board_pages_in_rank_order() {
        scorer("Third", 100);
        scorer("First", 300);
        scorer("Second", 200);

        List<LeaderboardEntry> all = walk(2, () -> {});

        assertThat(all).extracting(LeaderboardEntry::displayName).containsExactly("First", "Second", "Third");
        assertThat(all).extracting(LeaderboardEntry::rank).containsExactly(1L, 2L, 3L);
    }

    @Test
    void an_ascending_board_ranks_the_smallest_first() {
        Slug lapTimes = new Slug(unique("laps"));
        Leaderboard ascending =
                boards.save(Leaderboard.create(project, lapTimes, "Lap times", false, NOW));
        PlayerId quick = players.save(Player.firstSeen(PlayerId.random(), project, unique("d"), NOW).named("Quick", NOW)).id();
        PlayerId slow = players.save(Player.firstSeen(PlayerId.random(), project, unique("d"), NOW).named("Slow", NOW)).id();
        boards.submit(project, lapTimes, slow, 90, NOW);
        boards.submit(project, lapTimes, quick, 42, NOW);

        assertThat(boards.page(project, ascending, null, 10))
                .extracting(LeaderboardEntry::displayName)
                .containsExactly("Quick", "Slow");
    }

    @Test
    void tied_scores_are_still_a_total_order_so_paging_does_not_repeat_them() {
        // Everybody who finished the tutorial has the same score. Without the player_id tie-break
        // the cursor would sit in the middle of the tie and every page would start there again.
        for (int i = 0; i < 12; i++) {
            scorer("Tied " + i, 100);
        }

        List<LeaderboardEntry> all = walk(5, () -> {});

        assertThat(all).hasSize(12);
        assertThat(all.stream().map(LeaderboardEntry::playerId).distinct().count()).isEqualTo(12);
    }

    /**
     * The criterion itself.
     *
     * <p>Twenty players are walked five at a time while, between every page, a <em>different</em>
     * player's score is raised. Every row whose score did not change must appear exactly once.
     */
    @Test
    void walking_while_scores_change() {
        for (int i = 0; i < 20; i++) {
            scorer("Player " + i, 1000 - i * 10L);
        }
        // Two players whose scores will churn throughout, and which are therefore excluded from the
        // exactly-once assertion: they are allowed to move.
        PlayerId churnA = scorer("Churn A", 5);
        PlayerId churnB = scorer("Churn B", 6);

        long[] round = {0};
        List<LeaderboardEntry> seen =
                walk(
                        5,
                        () -> {
                            round[0]++;
                            boards.submit(project, boardId, churnA, 2000 + round[0], NOW);
                            boards.submit(project, boardId, churnB, 3000 + round[0], NOW);
                        });

        Set<PlayerId> churn = Set.of(churnA, churnB);
        List<PlayerId> stable =
                seen.stream().map(LeaderboardEntry::playerId).filter(id -> !churn.contains(id)).toList();

        assertThat(stable)
                .as("a row whose score did not change must be seen exactly once")
                .hasSize(20)
                .doesNotHaveDuplicates();
        assertThat(new HashSet<>(stable))
                .as("and every one of them must be seen")
                .hasSize(20);
    }

    @Test
    void a_score_is_kept_only_when_it_is_better() {
        PlayerId player = scorer("Player", 500);

        assertThat(boards.submit(project, boardId, player, 300, NOW))
                .as("a worse round must not drop a player's best")
                .isEqualTo(500);
        assertThat(boards.submit(project, boardId, player, 900, NOW)).isEqualTo(900);
    }

    @Test
    void on_an_ascending_board_better_means_smaller() {
        Slug lapTimes = new Slug(unique("laps"));
        boards.save(Leaderboard.create(project, lapTimes, "Lap times", false, NOW));
        PlayerId player = players.save(Player.firstSeen(PlayerId.random(), project, unique("d"), NOW)).id();

        boards.submit(project, lapTimes, player, 60, NOW);

        assertThat(boards.submit(project, lapTimes, player, 90, NOW)).isEqualTo(60);
        assertThat(boards.submit(project, lapTimes, player, 45, NOW)).isEqualTo(45);
    }

    @Test
    void a_players_own_rank_matches_where_they_appear_in_the_pages() {
        scorer("First", 300);
        PlayerId middle = scorer("Second", 200);
        scorer("Third", 100);

        assertThat(boards.entryOf(project, board, middle))
                .get()
                .extracting(LeaderboardEntry::rank)
                .isEqualTo(2L);
    }

    @Test
    void a_player_with_no_score_has_no_entry() {
        PlayerId silent = players.save(Player.firstSeen(PlayerId.random(), project, unique("d"), NOW)).id();

        assertThat(boards.entryOf(project, board, silent)).isEmpty();
    }

    @Test
    void deleting_a_player_removes_them_from_the_board() {
        PlayerId player = scorer("Player", 100);

        players.delete(project, player);

        assertThat(boards.count(project, boardId)).isZero();
    }

    @Test
    void deleting_a_board_removes_its_scores() {
        scorer("Player", 100);

        assertThat(boards.delete(project, boardId)).isTrue();
        assertThat(boards.find(project, boardId)).isEmpty();
    }
}
