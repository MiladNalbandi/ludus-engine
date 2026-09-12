// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.in;

import io.ludus.application.player.PlayerCaller;
import java.util.Optional;

/**
 * The player behind the request being handled.
 *
 * <p>The same shape as {@code CurrentCaller} and separate from it for the same reason the
 * principals are separate: a handler that wants a player must not be satisfied by an administrator,
 * and a handler that wants an administrator must not be satisfied by a player. Two ports make that
 * a compile-time distinction instead of a cast that happens to work.
 */
public interface CurrentPlayer {

    Optional<PlayerCaller> find();

    /**
     * @throws IllegalStateException when nothing authenticated this request as a player. Reaching a
     *     handler that calls this without one means a route was added without a matcher requiring
     *     {@code ROLE_PLAYER} — a wiring bug, not a client error, and the authorisation matrix test
     *     is what catches it.
     */
    default PlayerCaller require() {
        return find().orElseThrow(
                () -> new IllegalStateException(
                        "no authenticated player; this endpoint was reached without a filter chain"
                                + " rule requiring a player session token"));
    }
}
