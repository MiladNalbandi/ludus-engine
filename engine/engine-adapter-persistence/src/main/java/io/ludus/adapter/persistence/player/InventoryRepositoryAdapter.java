// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.InventoryRepository;
import io.ludus.domain.player.InventoryEntry;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/**
 * Inventory, adjusted the same way as a balance and for the same reasons.
 *
 * <p>One statement with the arithmetic in the database; an insert race retried rather than refused;
 * the below-zero guard left to the table's check rather than a test-then-write. All three are
 * explained at length in {@link WalletRepositoryAdapter}, and the second one is there because the
 * first version of that class got it wrong and a concurrency test found it.
 */
@Repository
public class InventoryRepositoryAdapter implements InventoryRepository {

    private final JdbcClient jdbc;

    InventoryRepositoryAdapter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public List<InventoryEntry> of(ProjectId projectId, PlayerId playerId) {
        return jdbc.sql(
                        """
                        select item_id, quantity, updated_at
                          from player_inventory
                         where project_id = :projectId and player_id = :playerId
                         order by item_id
                        """)
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .query(
                        (rs, row) ->
                                new InventoryEntry(
                                        new Slug(rs.getString("item_id")),
                                        rs.getLong("quantity"),
                                        rs.getTimestamp("updated_at").toInstant()))
                .list();
    }

    @Override
    @Transactional
    public Optional<InventoryEntry> adjust(
            ProjectId projectId, PlayerId playerId, Slug itemId, long delta, Instant at) {

        Instant when = at.truncatedTo(ChronoUnit.MICROS);

        try {
            if (add(projectId, playerId, itemId, delta, when) > 0) {
                return entry(projectId, playerId, itemId);
            }
        } catch (DataIntegrityViolationException refused) {
            return Optional.empty();
        }

        if (delta < 0) {
            return Optional.empty();
        }

        try {
            jdbc.sql(
                            """
                            insert into player_inventory
                                   (project_id, player_id, item_id, quantity, updated_at)
                            values (:projectId, :playerId, :itemId, :quantity, :at)
                            """)
                    .param("projectId", projectId.value())
                    .param("playerId", playerId.value())
                    .param("itemId", itemId.value())
                    .param("quantity", delta)
                    .param("at", java.sql.Timestamp.from(when))
                    .update();
        } catch (DataIntegrityViolationException raced) {
            // Either another thread created the row, or the item does not exist -- the composite
            // foreign key refuses both the same way. Retry the update: if it changes nothing, the
            // row still is not there, which means it was the item and not a race.
            try {
                if (add(projectId, playerId, itemId, delta, when) == 0) {
                    return Optional.empty();
                }
            } catch (DataIntegrityViolationException stillRefused) {
                return Optional.empty();
            }
        }

        return entry(projectId, playerId, itemId);
    }

    private int add(ProjectId projectId, PlayerId playerId, Slug itemId, long delta, Instant when) {
        return jdbc.sql(
                        """
                        update player_inventory
                           set quantity = quantity + :delta, updated_at = :at
                         where project_id = :projectId and player_id = :playerId and item_id = :itemId
                        """)
                .param("delta", delta)
                .param("at", java.sql.Timestamp.from(when))
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .param("itemId", itemId.value())
                .update();
    }

    private Optional<InventoryEntry> entry(ProjectId projectId, PlayerId playerId, Slug itemId) {
        return jdbc.sql(
                        """
                        select item_id, quantity, updated_at
                          from player_inventory
                         where project_id = :projectId and player_id = :playerId and item_id = :itemId
                        """)
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .param("itemId", itemId.value())
                .query(
                        (rs, row) ->
                                new InventoryEntry(
                                        new Slug(rs.getString("item_id")),
                                        rs.getLong("quantity"),
                                        rs.getTimestamp("updated_at").toInstant()))
                .optional();
    }
}
