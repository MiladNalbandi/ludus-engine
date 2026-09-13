// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.UnitOfWork;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.ProgressRepository;
import io.ludus.application.player.port.out.WalletRepository;
import io.ludus.domain.player.Balance;
import io.ludus.domain.player.CurrencyCode;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.player.XpStage;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

/**
 * Rewards, spending, and the XP curve.
 *
 * <p>The assertion the file exists for is that a reward is all or nothing. A player who received
 * the coins and not the gems has been given something the game never offered, and cannot be told
 * why — and the balances are right, so nothing looks broken.
 */
class PlayerEconomyTest {

    private static final Instant NOW = Instant.parse("2026-09-12T14:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final CurrencyCode COINS = new CurrencyCode("coins");
    private static final CurrencyCode GEMS = new CurrencyCode("gems");

    private final Players players = new Players();
    private final Wallet wallet = new Wallet();
    private final Progress progress = new Progress();
    private final RollingBack unitOfWork = new RollingBack();
    private final PlayerEconomy economy =
            new PlayerEconomy(players, wallet, progress, unitOfWork, Clock.fixed(NOW, ZoneOffset.UTC));

    private PlayerId aPlayer() {
        Player player = Player.firstSeen(PlayerId.random(), MINE, "device-one", NOW);
        players.save(player);
        return player.id();
    }

    @Test
    void a_grant_must_be_positive() {
        PlayerId player = aPlayer();

        assertThatThrownBy(() -> economy.grant(MINE, player, COINS, 0))
                .isInstanceOf(ContentRejected.class);
        assertThatThrownBy(() -> economy.grant(MINE, player, COINS, -5))
                .as("taking currency away is not a grant; it would be a silent debit")
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void granting_to_a_player_that_is_not_there_is_refused_before_any_write() {
        assertThatThrownBy(() -> economy.grant(MINE, PlayerId.random(), COINS, 10))
                .isInstanceOf(ContentRejected.class);
        assertThat(wallet.adjustments).isEmpty();
    }

    @Test
    void spending_more_than_the_balance_names_the_amount_rather_than_clamping() {
        PlayerId player = aPlayer();
        economy.grant(MINE, player, COINS, 10);

        assertThatThrownBy(() -> economy.spend(MINE, player, COINS, 50))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .singleElement()
                                        .extracting(ContentViolation::pointer)
                                        .isEqualTo("/amount"));
    }

    @Test
    void a_reward_applies_every_grant_and_the_xp() {
        PlayerId player = aPlayer();

        PlayerEconomy.Reward reward =
                economy.reward(
                        MINE,
                        player,
                        List.of(
                                new PlayerEconomy.Grant(COINS, 40),
                                new PlayerEconomy.Grant(GEMS, 2)),
                        100);

        assertThat(reward.balances())
                .extracting(b -> b.currency().value(), Balance::amount)
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("coins", 40L),
                        org.assertj.core.groups.Tuple.tuple("gems", 2L));
        assertThat(reward.xp()).isEqualTo(100);
    }

    @Test
    void one_bad_grant_rolls_the_whole_reward_back() {
        PlayerId player = aPlayer();

        assertThatThrownBy(
                        () ->
                                economy.reward(
                                        MINE,
                                        player,
                                        List.of(
                                                new PlayerEconomy.Grant(COINS, 40),
                                                new PlayerEconomy.Grant(GEMS, 0)),
                                        100))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/grants/1/amount"));

        assertThat(unitOfWork.rolledBack)
                .as("the transaction must have been rolled back, not merely the error reported")
                .isTrue();
    }

    @Test
    void a_reward_that_would_take_xp_away_is_refused() {
        PlayerId player = aPlayer();

        assertThatThrownBy(() -> economy.reward(MINE, player, List.of(), -10))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/xp"));
    }

    @Test
    void a_reward_of_nothing_is_allowed_and_changes_nothing() {
        PlayerId player = aPlayer();

        PlayerEconomy.Reward reward = economy.reward(MINE, player, List.of(), 0);

        assertThat(reward.balances()).isEmpty();
        assertThat(reward.xp()).isZero();
    }

    // ------------------------------------------------------------------ the curve

    @Test
    void a_project_with_no_curve_reports_no_stage_rather_than_stage_zero() {
        PlayerId player = aPlayer();
        economy.reward(MINE, player, List.of(), 500);

        PlayerEconomy.Progress reported = economy.progressOf(MINE, player);

        assertThat(reported.xp()).isEqualTo(500);
        assertThat(reported.stage())
                .as("inventing a stage would have a client render a progress bar out of nothing")
                .isNull();
        assertThat(reported.nextStage()).isNull();
    }

    @Test
    void the_stage_is_the_highest_threshold_reached() {
        economy.replaceCurve(
                MINE,
                List.of(
                        new XpStage(0, 0, "Rookie"),
                        new XpStage(1, 100, "Adept"),
                        new XpStage(2, 500, "Veteran")));
        PlayerId player = aPlayer();
        economy.reward(MINE, player, List.of(), 250);

        PlayerEconomy.Progress reported = economy.progressOf(MINE, player);

        assertThat(reported.stage().stage()).isEqualTo(1);
        assertThat(reported.nextStage().stage()).isEqualTo(2);
        assertThat(reported.nextStage().xpRequired()).isEqualTo(500);
    }

    @Test
    void at_the_top_of_the_curve_there_is_no_next_stage() {
        economy.replaceCurve(MINE, List.of(new XpStage(0, 0, "Rookie"), new XpStage(1, 100, "Adept")));
        PlayerId player = aPlayer();
        economy.reward(MINE, player, List.of(), 1000);

        assertThat(economy.progressOf(MINE, player).nextStage()).isNull();
    }

    @Test
    void a_curve_whose_later_stage_begins_earlier_is_refused_with_the_index() {
        assertThatThrownBy(
                        () ->
                                economy.replaceCurve(
                                        MINE,
                                        List.of(
                                                new XpStage(0, 0, "Rookie"),
                                                new XpStage(1, 500, "Adept"),
                                                new XpStage(2, 200, "Veteran"))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/stages/2/xpRequired"));
    }

    @Test
    void a_curve_listing_one_stage_twice_is_refused() {
        assertThatThrownBy(
                        () ->
                                economy.replaceCurve(
                                        MINE,
                                        List.of(new XpStage(1, 100, "A"), new XpStage(1, 200, "B"))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .contains("/stages/1/stage"));
    }

    @Test
    void an_empty_curve_is_allowed_because_a_project_may_have_no_stages() {
        assertThat(economy.replaceCurve(MINE, List.of())).isEmpty();
    }

    // ------------------------------------------------------------------ fakes

    /** Records whether the work was rolled back, which is what "all or nothing" means here. */
    private static final class RollingBack implements UnitOfWork {
        private boolean rolledBack;

        @Override
        public <T> T inOne(Supplier<T> work) {
            try {
                return work.get();
            } catch (RuntimeException thrown) {
                rolledBack = true;
                throw thrown;
            }
        }
    }

    private static final class Wallet implements WalletRepository {
        private final Map<String, Balance> balances = new LinkedHashMap<>();
        private final List<String> adjustments = new ArrayList<>();

        private static String key(PlayerId player, CurrencyCode currency) {
            return player + "/" + currency;
        }

        @Override
        public List<Balance> balances(ProjectId projectId, PlayerId playerId) {
            return balances.entrySet().stream()
                    .filter(entry -> entry.getKey().startsWith(playerId + "/"))
                    .map(Map.Entry::getValue)
                    .toList();
        }

        @Override
        public Optional<Balance> adjust(
                ProjectId projectId, PlayerId playerId, CurrencyCode currency, long delta, Instant at) {
            adjustments.add(key(playerId, currency) + ":" + delta);
            Balance existing = balances.get(key(playerId, currency));
            long next = (existing == null ? 0 : existing.amount()) + delta;
            if (next < 0) {
                // The real one lets the database's check refuse it; the fake has to refuse too, or
                // a test would pass here and fail against a real schema.
                return Optional.empty();
            }
            Balance updated = new Balance(currency, next, at);
            balances.put(key(playerId, currency), updated);
            return Optional.of(updated);
        }
    }

    private static final class Progress implements ProgressRepository {
        private final Map<PlayerId, Long> xp = new HashMap<>();
        private List<XpStage> curve = List.of();

        @Override
        public long xp(ProjectId projectId, PlayerId playerId) {
            return xp.getOrDefault(playerId, 0L);
        }

        @Override
        public Optional<Long> addXp(ProjectId projectId, PlayerId playerId, long delta, Instant at) {
            long next = xp(projectId, playerId) + delta;
            if (next < 0) {
                return Optional.empty();
            }
            xp.put(playerId, next);
            return Optional.of(next);
        }

        @Override
        public List<XpStage> curve(ProjectId projectId) {
            return curve;
        }

        @Override
        public List<XpStage> replaceCurve(ProjectId projectId, List<XpStage> stages) {
            curve = List.copyOf(stages);
            return curve;
        }
    }

    private static final class Players implements PlayerRepository {
        private final Map<PlayerId, Player> saved = new LinkedHashMap<>();

        @Override
        public Player save(Player player) {
            saved.put(player.id(), player);
            return player;
        }

        @Override
        public Optional<Player> find(ProjectId projectId, PlayerId id) {
            return Optional.ofNullable(saved.get(id)).filter(p -> p.projectId().equals(projectId));
        }

        @Override
        public Optional<Player> findByExternalId(ProjectId projectId, String externalId) {
            return saved.values().stream()
                    .filter(p -> p.projectId().equals(projectId) && p.externalId().equals(externalId))
                    .findFirst();
        }

        @Override
        public List<Player> page(ProjectId projectId, PlayerPageCursor after, int limit) {
            return saved.values().stream().filter(p -> p.projectId().equals(projectId)).limit(limit).toList();
        }

        @Override
        public long count(ProjectId projectId) {
            return saved.values().stream().filter(p -> p.projectId().equals(projectId)).count();
        }

        @Override
        public boolean delete(ProjectId projectId, PlayerId id) {
            return find(projectId, id).isPresent() && saved.remove(id) != null;
        }
    }
}
