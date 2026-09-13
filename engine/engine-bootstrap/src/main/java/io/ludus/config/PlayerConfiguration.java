// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.content.port.out.UnitOfWork;
import io.ludus.application.player.PlayerEconomy;
import io.ludus.application.player.PlayerSessions;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.PlayerTokenIssuer;
import io.ludus.application.player.port.out.ProgressRepository;
import io.ludus.application.player.port.out.WalletRepository;
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

    @Bean
    public PlayerEconomy playerEconomy(
            PlayerRepository players,
            WalletRepository wallet,
            ProgressRepository progress,
            UnitOfWork unitOfWork,
            Clock clock) {
        return new PlayerEconomy(players, wallet, progress, unitOfWork, clock);
    }
}
