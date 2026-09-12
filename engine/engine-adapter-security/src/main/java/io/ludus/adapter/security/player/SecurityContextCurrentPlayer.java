// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.player;

import io.ludus.application.player.PlayerCaller;
import io.ludus.application.player.port.in.CurrentPlayer;
import java.util.Optional;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

/**
 * Reads the player out of Spring's security context.
 *
 * <p>The {@code instanceof} is what keeps the two principals apart. An administrator's request
 * carries a {@code Caller}, and asking this for a player returns empty rather than casting — so a
 * route that wanted a player and was wired to accept anybody authenticated fails loudly at the
 * {@code require()} rather than reading somebody else's id out of the wrong type.
 */
@Component
public class SecurityContextCurrentPlayer implements CurrentPlayer {

    @Override
    public Optional<PlayerCaller> find() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated()) {
            return Optional.empty();
        }
        return authentication.getPrincipal() instanceof PlayerCaller player
                ? Optional.of(player)
                : Optional.empty();
    }
}
