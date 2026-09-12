// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.Player;
import java.time.Instant;

/**
 * Mints the token a game client presents when acting as one player.
 *
 * <p>A separate port from {@code AccessTokenIssuer}, and separate for a reason worth stating: the
 * two answer different questions. An access token says which <em>person</em> is administering the
 * project; this says which <em>player</em> a client is currently playing as. Issuing both from one
 * place would mean one bug could turn a player into an editor.
 */
public interface PlayerTokenIssuer {

    String issue(Player player, Instant issuedAt, Instant expiresAt);
}
