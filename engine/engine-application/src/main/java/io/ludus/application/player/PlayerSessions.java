// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.PlayerTokenIssuer;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

/**
 * Starting a player's session, and the credential question that shapes all of live-ops.
 *
 * <p><b>Issue #10 asks that "a game client can read and write player state with an API key". It
 * cannot, and this is where that is resolved rather than quietly implemented.</b>
 *
 * <p>An API key is deliberately {@code VIEWER}-only, and the reason is written into
 * {@code ApiKeys}: a key ships inside a binary anybody can download and unpack, so anything it can
 * do should be assumed public. Letting a shipped key write player state would mean anyone who
 * unpacked the game could write <em>any</em> player's balance, inventory and scores. That is not a
 * stricter reading of the requirement; it is the requirement being impossible as stated.
 *
 * <p>So the key keeps the job it is good at — saying which game build is calling, and which project
 * — and it buys a <b>player session token</b>: short-lived, scoped to exactly one player, and the
 * only credential that can write that player's state. A leaked API key then lets an attacker play
 * as a player of their own, which is unavoidable for any credential that ships to a client. It does
 * not let them touch anybody else's.
 *
 * <p>The engine does not authenticate the player. It cannot: it has no password for them and
 * deliberately holds no account. The game vouches for the identifier, which means a game with no
 * server of its own gets device-level trust — honest, and stated in the documentation rather than
 * implied to be more.
 */
public class PlayerSessions {

    /**
     * Short, because this token authorises writes and cannot be revoked.
     *
     * <p>The same trade as the administrative access token: verified by a signature and nothing
     * else, which is what makes it cheap, and therefore valid until it expires whatever happens.
     * An hour is long enough for a play session and short enough that a token lifted off a device
     * stops being useful quickly.
     */
    public static final Duration SESSION_LIFETIME = Duration.ofHours(1);

    private final PlayerRepository players;
    private final PlayerTokenIssuer tokens;
    private final Clock clock;

    public PlayerSessions(PlayerRepository players, PlayerTokenIssuer tokens, Clock clock) {
        this.players = players;
        this.tokens = tokens;
        this.clock = clock;
    }

    /**
     * Resolves the game's identifier to a player and issues a session token.
     *
     * <p>Creates the player on first sight. There is no separate registration call, because a
     * client would have to decide which to call and would get it wrong on exactly the path that
     * matters — a reinstall, where the game has an identifier and the engine has a row it has
     * forgotten about, or the reverse.
     *
     * <p>Idempotent by the unique index on {@code (project_id, external_id)}: a client retrying
     * through a network blip finds the player it just created rather than making a second one whose
     * predecessor's progress is unreachable.
     */
    public Session start(ProjectId projectId, String externalId) {
        if (externalId == null || externalId.isBlank()) {
            throw new IllegalArgumentException("a session needs the game's identifier for the player");
        }
        Instant now = clock.instant();

        Player player =
                players.findByExternalId(projectId, externalId.trim())
                        .map(existing -> players.save(existing.seenAt(now)))
                        .orElseGet(
                                () ->
                                        players.save(
                                                Player.firstSeen(
                                                        PlayerId.random(), projectId, externalId, now)));

        Instant expiresAt = now.plus(SESSION_LIFETIME);
        return new Session(player, tokens.issue(player, now, expiresAt), expiresAt);
    }

    public Optional<Player> find(ProjectId projectId, PlayerId id) {
        return players.find(projectId, id);
    }

    /** Renames a player. Theirs to set; the engine never derives one. */
    public Optional<Player> rename(ProjectId projectId, PlayerId id, String displayName) {
        return players.find(projectId, id)
                .map(player -> players.save(player.named(displayName, clock.instant())));
    }

    /** A player, the token that acts as them, and when it stops working. */
    public record Session(Player player, String token, Instant expiresAt) {}
}
