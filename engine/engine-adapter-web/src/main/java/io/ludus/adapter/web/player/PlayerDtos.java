// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.PlayerSessions;
import io.ludus.domain.player.Player;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

final class PlayerDtos {

    private PlayerDtos() {}

    @Schema(name = "PlayerSessionRequest", description = "The game's own identifier for this player.")
    record SessionRequest(String externalId) {}

    /**
     * A session. The token is shown once per session and held in memory by the client.
     *
     * <p>The external id is echoed back so a client can confirm the engine resolved the identifier
     * it meant — a silent mismatch would show up as a player whose progress is mysteriously empty.
     */
    @Schema(name = "PlayerSession", description = "A player session token and who it acts as.")
    record Session(
            String playerId, String externalId, String displayName, String token, Instant expiresAt) {

        static Session of(PlayerSessions.Session session) {
            return new Session(
                    session.player().id().toString(),
                    session.player().externalId(),
                    session.player().displayName(),
                    session.token(),
                    session.expiresAt());
        }
    }

    /**
     * A player, as themselves or as an administrator sees them.
     *
     * <p>The external id is included, and that is a deliberate call: it is the game's own
     * identifier, which for many games is a device id. It is shown to the player it belongs to and
     * to an administrator, and to nobody else — there is no route that returns another player's
     * profile, which is why there is one DTO rather than a public and a private variant.
     */
    @Schema(name = "PlayerProfile", description = "A player's identity and when they were last seen.")
    record Profile(
            String id, String externalId, String displayName, Instant createdAt, Instant lastSeenAt) {

        static Profile of(Player player) {
            return new Profile(
                    player.id().toString(),
                    player.externalId(),
                    player.displayName(),
                    player.createdAt(),
                    player.lastSeenAt());
        }
    }

    @Schema(name = "PlayerRenameRequest", description = "A display name the player chose. Blank clears it.")
    record RenameRequest(String displayName) {}

    /**
     * A page of players, with the cursor for the next one.
     *
     * <p>A cursor rather than a page number. `last_seen_at` changes on every session, so an offset
     * would skip and repeat players as they play — the instability is not hypothetical here, it is
     * the ordering column's normal behaviour.
     */
    @Schema(name = "PlayerPage", description = "Players, most recently seen first, with a cursor.")
    record Page(List<Profile> players, long total, String nextCursor) {}

    @Schema(name = "PlayerBalance", description = "How much of one currency a player has.")
    record BalanceView(String currency, long amount, Instant updatedAt) {

        static BalanceView of(io.ludus.domain.player.Balance balance) {
            return new BalanceView(
                    balance.currency().value(), balance.amount(), balance.updatedAt());
        }
    }

    @Schema(name = "PlayerWallet", description = "Every currency this player holds.")
    record Wallet(List<BalanceView> balances) {}

    @Schema(name = "PlayerSpendRequest", description = "How much of which currency to spend.")
    record SpendRequest(String currency, Long amount) {}

    @Schema(name = "PlayerGrantRequest", description = "How much of which currency to award.")
    record GrantRequest(String currency, Long amount) {}

    @Schema(name = "PlayerRewardRequest", description = "Currencies and XP to award together, or not at all.")
    record RewardRequest(List<GrantRequest> grants, Long xp) {}

    @Schema(name = "XpStageView", description = "One step of the project's XP curve.")
    record StageView(int stage, long xpRequired, String label) {

        static StageView of(io.ludus.domain.player.XpStage stage) {
            return stage == null ? null : new StageView(stage.stage(), stage.xpRequired(), stage.label());
        }
    }

    /**
     * A player's XP and where it puts them.
     *
     * <p>{@code stage} and {@code nextStage} are null when the project has defined no curve, which
     * is the honest answer rather than inventing a stage 0 for a client to render.
     */
    @Schema(name = "PlayerProgress", description = "XP, the stage reached, and the next one.")
    record ProgressView(long xp, StageView stage, StageView nextStage) {

        static ProgressView of(io.ludus.application.player.PlayerEconomy.Progress progress) {
            return new ProgressView(
                    progress.xp(),
                    StageView.of(progress.stage()),
                    StageView.of(progress.nextStage()));
        }
    }

    @Schema(name = "PlayerRewardResult", description = "What a reward left behind.")
    record RewardView(List<BalanceView> balances, long xp, StageView stage) {

        static RewardView of(io.ludus.application.player.PlayerEconomy.Reward reward) {
            return new RewardView(
                    reward.balances().stream().map(BalanceView::of).toList(),
                    reward.xp(),
                    StageView.of(reward.stage()));
        }
    }

    @Schema(name = "XpCurve", description = "The project's XP curve, in ascending order.")
    record Curve(List<StageView> stages) {}
}
