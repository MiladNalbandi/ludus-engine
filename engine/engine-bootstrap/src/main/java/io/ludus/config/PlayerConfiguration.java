// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.player.PlayerSessions;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.PlayerTokenIssuer;
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Wires the live-ops use cases.
 *
 * <p>They are plain objects with constructor arguments, like every other use case here: the
 * application module carries no Spring annotations, so this module is the only place that knows how
 * they are assembled.
 */
@Configuration(proxyBeanMethods = false)
public class PlayerConfiguration {

    @Bean
    public PlayerSessions playerSessions(
            PlayerRepository players, PlayerTokenIssuer tokens, Clock clock) {
        return new PlayerSessions(players, tokens, clock);
    }
}
