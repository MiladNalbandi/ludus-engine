// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import java.time.Instant;

/** How much of one currency a player has. */
public record Balance(CurrencyCode currency, long amount, Instant updatedAt) {

    public Balance {
        if (currency == null) {
            throw new IllegalArgumentException("a balance must name its currency");
        }
        if (amount < 0) {
            // Also a database check. Here as well, because a domain object that can hold an
            // impossible value is one that will be constructed with an impossible value in a test
            // and pass.
            throw new IllegalArgumentException("a balance must not be negative, was " + amount);
        }
        if (updatedAt == null) {
            throw new IllegalArgumentException("a balance must carry its timestamp");
        }
    }
}
