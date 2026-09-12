// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.UnitOfWork;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.ProgressRepository;
import io.ludus.application.player.port.out.WalletRepository;
import io.ludus.domain.player.Balance;
import io.ludus.domain.player.CurrencyCode;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.player.XpStage;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * What a player has and how far they have got.
 *
 * <p><b>Who may credit, and who may only spend.</b> A grant is authorised by an editor or above; a
 * spend may be made by the player themselves. That asymmetry is the whole of the trust model and is
 * worth being explicit about, because the obvious alternative — letting the client award its own
 * rewards — means the currency is whatever the player's modified binary says it is.
 *
 * <p>Spending is safe to expose to a client because it can only reduce the player's own balance:
 * the worst a forged spend does is cost the person who forged it. Crediting is not, so it needs a
 * credential that does not ship inside the game. A game with no server of its own therefore cannot
 * award currency through Ludus, and that is a real limitation stated plainly rather than a hole
 * left open to avoid admitting it.
 */
public class PlayerEconomy {

    private final PlayerRepository players;
    private final WalletRepository wallet;
    private final ProgressRepository progress;
    private final UnitOfWork unitOfWork;
    private final Clock clock;

    public PlayerEconomy(
            PlayerRepository players,
            WalletRepository wallet,
            ProgressRepository progress,
            UnitOfWork unitOfWork,
            Clock clock) {
        this.players = players;
        this.wallet = wallet;
        this.progress = progress;
        this.unitOfWork = unitOfWork;
        this.clock = clock;
    }

    public List<Balance> balances(ProjectId projectId, PlayerId playerId) {
        return wallet.balances(projectId, playerId);
    }

    /**
     * Credits a player. Editor and above only.
     *
     * @throws ContentRejected when the amount is not positive, or the player is not there
     */
    public Balance grant(ProjectId projectId, PlayerId playerId, CurrencyCode currency, long amount) {
        if (amount <= 0) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/amount", "a grant must be more than zero")));
        }
        requirePlayer(projectId, playerId);

        return wallet.adjust(projectId, playerId, currency, amount, clock.instant())
                .orElseThrow(
                        () ->
                                new ContentRejected(
                                        List.of(
                                                ContentViolation.atRoot(
                                                        "that grant could not be applied"))));
    }

    /**
     * Spends from a player's own balance.
     *
     * <p>Refused rather than clamped when they cannot afford it. A spend that quietly took the
     * balance to zero would let a client buy what it could not pay for, with the engine agreeing.
     */
    public Balance spend(ProjectId projectId, PlayerId playerId, CurrencyCode currency, long amount) {
        if (amount <= 0) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/amount", "a spend must be more than zero")));
        }

        return wallet.adjust(projectId, playerId, currency, -amount, clock.instant())
                .orElseThrow(
                        () ->
                                new ContentRejected(
                                        List.of(
                                                new ContentViolation(
                                                        "/amount",
                                                        "not enough " + currency + " to spend " + amount))));
    }

    /**
     * Several changes to one player, all or nothing.
     *
     * <p>This is what a "reward" is: a quest gives forty coins, two gems and a hundred XP, and a
     * player who received the coins and not the gems has been given something the game never
     * offered. Sharing one transaction means the answer is always all of it or none.
     */
    public Reward reward(
            ProjectId projectId, PlayerId playerId, List<Grant> grants, long xp) {
        requirePlayer(projectId, playerId);
        if (grants == null) {
            grants = List.of();
        }
        List<Grant> requested = grants;

        return unitOfWork.inOne(
                () -> {
                    Instant now = clock.instant();
                    List<ContentViolation> violations = new ArrayList<>();
                    List<Balance> after = new ArrayList<>();

                    for (int index = 0; index < requested.size(); index++) {
                        Grant grant = requested.get(index);
                        if (grant.amount() <= 0) {
                            violations.add(
                                    new ContentViolation(
                                            "/grants/" + index + "/amount",
                                            "a reward's grant must be more than zero"));
                            continue;
                        }
                        Optional<Balance> balance =
                                wallet.adjust(projectId, playerId, grant.currency(), grant.amount(), now);
                        if (balance.isEmpty()) {
                            violations.add(
                                    new ContentViolation(
                                            "/grants/" + index, "that grant could not be applied"));
                            continue;
                        }
                        after.add(balance.get());
                    }

                    long total = progress.xp(projectId, playerId);
                    if (xp < 0) {
                        violations.add(new ContentViolation("/xp", "a reward must not take XP away"));
                    } else if (xp > 0) {
                        total =
                                progress.addXp(projectId, playerId, xp, now)
                                        .orElseGet(() -> progress.xp(projectId, playerId));
                    }

                    if (!violations.isEmpty()) {
                        // Rolls back every grant above, including the ones that succeeded.
                        throw new ContentRejected(violations);
                    }

                    return new Reward(List.copyOf(after), total, stageOf(projectId, total));
                });
    }

    /** A player's XP and where that puts them on the project's curve. */
    public Progress progressOf(ProjectId projectId, PlayerId playerId) {
        long xp = progress.xp(projectId, playerId);
        List<XpStage> curve = progress.curve(projectId);
        return new Progress(
                xp, XpStage.reached(curve, xp).orElse(null), XpStage.next(curve, xp).orElse(null));
    }

    public List<XpStage> curve(ProjectId projectId) {
        return progress.curve(projectId);
    }

    /**
     * Replaces the project's XP curve.
     *
     * <p>Wholesale, because the stages are only meaningful relative to each other: editing one in
     * isolation can leave two stages with the same threshold, or a stage 3 that begins before stage
     * 2. Validated here so an author gets every problem at once with the index that caused it.
     */
    public List<XpStage> replaceCurve(ProjectId projectId, List<XpStage> stages) {
        if (stages == null) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/stages", "send the stages, even an empty list")));
        }

        List<ContentViolation> violations = new ArrayList<>();
        List<XpStage> sorted =
                stages.stream().sorted(java.util.Comparator.comparingInt(XpStage::stage)).toList();

        for (int index = 0; index < sorted.size(); index++) {
            XpStage stage = sorted.get(index);
            if (index > 0) {
                XpStage previous = sorted.get(index - 1);
                if (stage.stage() == previous.stage()) {
                    violations.add(
                            new ContentViolation(
                                    "/stages/" + index + "/stage",
                                    "stage " + stage.stage() + " is listed twice"));
                }
                if (stage.xpRequired() <= previous.xpRequired()) {
                    // A later stage that begins at or before an earlier one makes "which stage is
                    // this" ambiguous, and the unique index would refuse it anyway -- as a
                    // constraint name rather than as something an author can act on.
                    violations.add(
                            new ContentViolation(
                                    "/stages/" + index + "/xpRequired",
                                    "stage "
                                            + stage.stage()
                                            + " must begin after stage "
                                            + previous.stage()
                                            + ", which begins at "
                                            + previous.xpRequired()));
                }
            }
        }

        if (!violations.isEmpty()) {
            throw new ContentRejected(violations);
        }
        return progress.replaceCurve(projectId, sorted);
    }

    private XpStage stageOf(ProjectId projectId, long xp) {
        return XpStage.reached(progress.curve(projectId), xp).orElse(null);
    }

    private void requirePlayer(ProjectId projectId, PlayerId playerId) {
        if (players.find(projectId, playerId).isEmpty()) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("no such player in this project")));
        }
    }

    /** One currency and how much of it to add. */
    public record Grant(CurrencyCode currency, long amount) {}

    /** What a reward left behind. {@code stage} is null when the project has no curve. */
    public record Reward(List<Balance> balances, long xp, XpStage stage) {}

    /** Where a player is. Both stages are null when the project has defined no curve. */
    public record Progress(long xp, XpStage stage, XpStage nextStage) {}
}
