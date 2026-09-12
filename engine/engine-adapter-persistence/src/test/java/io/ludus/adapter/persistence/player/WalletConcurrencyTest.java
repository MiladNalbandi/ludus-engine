// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.adapter.persistence.project.ProjectRepositoryAdapter;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.ProgressRepository;
import io.ludus.application.player.port.out.WalletRepository;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.player.Balance;
import io.ludus.domain.player.CurrencyCode;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;
import org.assertj.core.groups.Tuple;
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
 * The balance rules, against a real schema and real concurrency.
 *
 * <p>Three of these fail against the obvious implementation — read the balance, add in Java, write
 * it back — and none of them fails visibly in production. A lost update is not an error: two grants
 * arriving together both read 100, both write 110, and one is simply gone. The player is short,
 * nothing is logged, and the only way to find it is to look for it on purpose.
 *
 * <p><b>{@code NOT_SUPPORTED} rather than the usual rollback, and it has to be.</b> {@code
 * @DataJpaTest} wraps each test in a transaction it rolls back, which is right for everything else
 * in this module and impossible here: the worker threads run their own transactions and cannot see
 * a player created in one that has not committed. The first version of this had every concurrent
 * grant fail on the foreign key and assert a balance of zero — which looks exactly like a lost
 * update and is not one.
 *
 * <p>Which means the rows it writes are committed, and <b>that needs its own database</b>. The
 * first version shared the module's, and its committed projects collided with
 * {@code ProjectRepositoryAdapterTest}'s {@code default} slug — passing locally on test ordering
 * and failing on CI, which is the worst way to find out. A separate in-memory URL makes the
 * isolation structural rather than a matter of who runs first.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
@TestPropertySource(
        properties =
                "spring.datasource.url="
                        + "jdbc:h2:mem:ludus-wallet-concurrency"
                        + ";DB_CLOSE_DELAY=-1;MODE=PostgreSQL;DATABASE_TO_LOWER=TRUE")
@Import({
    ProjectRepositoryAdapter.class,
    PlayerRepositoryAdapter.class,
    WalletRepositoryAdapter.class,
    ProgressRepositoryAdapter.class
})
class WalletConcurrencyTest {

    private static final Instant NOW = Instant.parse("2026-09-12T14:00:00Z");
    private static final CurrencyCode COINS = new CurrencyCode("coins");

    @Autowired private ProjectRepository projects;
    @Autowired private PlayerRepository players;
    @Autowired private WalletRepository wallet;
    @Autowired private ProgressRepository progress;

    private ProjectId project;
    private ProjectId otherProject;
    private PlayerId player;

    /** Unique per test, because nothing is rolled back between them. */
    private static String unique(String prefix) {
        return prefix + "_" + Long.toString(System.nanoTime(), 36);
    }

    @BeforeEach
    void aPlayerInEachOfTwoProjects() {
        project = projects.save(Project.create(new Slug(unique("mine")), "Mine", NOW)).id();
        otherProject = projects.save(Project.create(new Slug(unique("theirs")), "Theirs", NOW)).id();
        player = players.save(Player.firstSeen(PlayerId.random(), project, unique("device"), NOW)).id();
    }

    private long balance() {
        return wallet.balances(project, player).stream()
                .filter(b -> b.currency().equals(COINS))
                .mapToLong(Balance::amount)
                .findFirst()
                .orElse(0L);
    }

    @Test
    void a_first_grant_creates_the_balance() {
        assertThat(wallet.adjust(project, player, COINS, 100, NOW))
                .get()
                .extracting(Balance::amount)
                .isEqualTo(100L);
        assertThat(balance()).isEqualTo(100L);
    }

    @Test
    void spending_reduces_it() {
        wallet.adjust(project, player, COINS, 100, NOW);

        assertThat(wallet.adjust(project, player, COINS, -30, NOW))
                .get()
                .extracting(Balance::amount)
                .isEqualTo(70L);
    }

    @Test
    void spending_more_than_the_balance_is_refused_rather_than_clamped() {
        wallet.adjust(project, player, COINS, 50, NOW);

        assertThat(wallet.adjust(project, player, COINS, -80, NOW))
                .as("a clamped spend would let a client buy what it cannot afford")
                .isEmpty();
        assertThat(balance()).as("and must leave the balance alone").isEqualTo(50L);
    }

    @Test
    void spending_from_nothing_is_refused() {
        assertThat(wallet.adjust(project, player, COINS, -1, NOW)).isEmpty();
        assertThat(balance()).isZero();
    }

    @Test
    void spending_exactly_the_balance_is_allowed() {
        wallet.adjust(project, player, COINS, 40, NOW);

        assertThat(wallet.adjust(project, player, COINS, -40, NOW))
                .get()
                .extracting(Balance::amount)
                .isEqualTo(0L);
    }

    /**
     * The one that catches a read-modify-write.
     *
     * <p>Twenty concurrent grants of one coin. The arithmetic happens in the database, so the total
     * is twenty however they interleave. Done in Java the reads overlap, the writes overwrite each
     * other, and the total is some number below twenty that changes every run.
     */
    @Test
    void concurrent_grants_do_not_lose_each_other() throws Exception {
        int grants = 20;
        var pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Object>> work =
                    IntStream.range(0, grants)
                            .<Callable<Object>>mapToObj(
                                    i -> () -> wallet.adjust(project, player, COINS, 1, NOW))
                            .toList();
            for (Future<Object> done : pool.invokeAll(work)) {
                done.get();
            }
        } finally {
            pool.shutdownNow();
        }

        assertThat(balance())
                .as("every grant must be there; a lost update is silent and leaves the player short")
                .isEqualTo(grants);
    }

    /** The same for XP, accumulated the same way and lost the same way. */
    @Test
    void concurrent_xp_awards_do_not_lose_each_other() throws Exception {
        int awards = 20;
        var pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Object>> work =
                    IntStream.range(0, awards)
                            .<Callable<Object>>mapToObj(i -> () -> progress.addXp(project, player, 5, NOW))
                            .toList();
            for (Future<Object> done : pool.invokeAll(work)) {
                done.get();
            }
        } finally {
            pool.shutdownNow();
        }

        assertThat(progress.xp(project, player)).isEqualTo(awards * 5L);
    }

    /**
     * Twenty attempts to spend one coin from a balance of ten.
     *
     * <p>Ten must succeed and ten must fail. A check-then-act lets more through, because the gap
     * between reading the balance and writing it is exactly where another spend fits — and the
     * result is a negative balance the schema was supposed to make impossible.
     */
    @Test
    void concurrent_spends_cannot_overdraw() throws Exception {
        wallet.adjust(project, player, COINS, 10, NOW);

        int succeeded = 0;
        var pool = Executors.newFixedThreadPool(8);
        try {
            List<Callable<Boolean>> work =
                    IntStream.range(0, 20)
                            .<Callable<Boolean>>mapToObj(
                                    i -> () -> wallet.adjust(project, player, COINS, -1, NOW).isPresent())
                            .toList();
            for (Future<Boolean> done : pool.invokeAll(work)) {
                if (done.get()) {
                    succeeded++;
                }
            }
        } finally {
            pool.shutdownNow();
        }

        assertThat(succeeded).isEqualTo(10);
        assertThat(balance()).isZero();
    }

    @Test
    void balances_are_scoped_to_the_project() {
        wallet.adjust(project, player, COINS, 100, NOW);

        assertThat(wallet.balances(otherProject, player))
                .as("the composite foreign key means this player is not in that project at all")
                .isEmpty();
    }

    @Test
    void several_currencies_are_independent() {
        wallet.adjust(project, player, COINS, 100, NOW);
        wallet.adjust(project, player, new CurrencyCode("gems"), 5, NOW);

        assertThat(wallet.balances(project, player))
                .extracting(b -> b.currency().value(), Balance::amount)
                .containsExactly(Tuple.tuple("coins", 100L), Tuple.tuple("gems", 5L));
    }

    @Test
    void deleting_a_player_takes_their_balances_with_them() {
        wallet.adjust(project, player, COINS, 100, NOW);

        // Deleted through the repository, so the cascade under test is the schema's rather than
        // one this test arranged.
        players.delete(project, player);

        assertThat(wallet.balances(project, player))
                .as("by foreign key, so no delete path can leave orphaned money behind")
                .isEmpty();
    }
}
