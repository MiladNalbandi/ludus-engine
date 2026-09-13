// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.InventoryEntry;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** What players hold. */
public interface InventoryRepository {

    List<InventoryEntry> of(ProjectId projectId, PlayerId playerId);

    /**
     * Adds to a quantity, or subtracts when the delta is negative.
     *
     * <p>One statement, with the arithmetic in the database, for the same reason as a balance: a
     * read-modify-write loses grants that arrive together, and loses them silently. A subtraction
     * that would go below zero is refused by the table's check rather than by a test-then-write
     * with a gap in the middle.
     *
     * @return the entry afterwards, or empty when the change was refused
     */
    Optional<InventoryEntry> adjust(
            ProjectId projectId, PlayerId playerId, Slug itemId, long delta, Instant at);
}
