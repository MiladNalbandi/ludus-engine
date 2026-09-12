// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import io.ludus.domain.shared.Slug;
import java.time.Instant;

/**
 * How many of one item a player has.
 *
 * <p>Zero is a real value, not an absence. "Had one and used it" is worth telling apart from "never
 * had one" when a game shows a collection, and a row that disappeared at zero would make the two
 * indistinguishable.
 */
public record InventoryEntry(Slug itemId, long quantity, Instant updatedAt) {

    public InventoryEntry {
        if (itemId == null) {
            throw new IllegalArgumentException("an inventory entry must name its item");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("an inventory quantity must not be negative");
        }
        if (updatedAt == null) {
            throw new IllegalArgumentException("an inventory entry must carry its timestamp");
        }
    }
}
