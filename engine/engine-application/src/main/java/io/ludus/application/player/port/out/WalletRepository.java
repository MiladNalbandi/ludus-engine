// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.Balance;
import io.ludus.domain.player.CurrencyCode;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.List;

/** Balances, and the one operation that changes them. */
public interface WalletRepository {

    List<Balance> balances(ProjectId projectId, PlayerId playerId);

    /**
     * Adds to a balance, or subtracts when the delta is negative.
     *
     * <p><b>One statement, and the arithmetic happens in the database.</b> The obvious
     * implementation — read the balance, add in Java, write it back — loses updates: two grants
     * arriving together both read 100, both write 110, and one of them is simply gone. Nothing
     * fails, nobody notices, and the player is short. {@code set amount = amount + :delta} cannot
     * do that, because the read and the write are the same operation.
     *
     * <p>Refuses rather than clamping when a debit would go below zero. A spend that silently took
     * a balance to zero instead of failing would let a client buy something it could not afford,
     * and the engine would have agreed.
     *
     * @return the balance afterwards, or empty when the change was refused
     */
    java.util.Optional<Balance> adjust(
            ProjectId projectId, PlayerId playerId, CurrencyCode currency, long delta, Instant at);
}
