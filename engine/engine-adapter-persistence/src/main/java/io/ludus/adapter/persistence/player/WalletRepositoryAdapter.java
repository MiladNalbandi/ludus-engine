// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.WalletRepository;
import io.ludus.domain.player.Balance;
import io.ludus.domain.player.CurrencyCode;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/**
 * Balances, adjusted in one statement.
 *
 * <p><b>JDBC rather than JPA, deliberately.</b> An entity here would mean loading a balance,
 * changing a field and letting Hibernate write it back — a read-modify-write, which loses updates:
 * two grants arriving together both read 100, both write 110, and one is simply gone. Nothing
 * fails, nobody notices, and the player is short. The arithmetic has to happen in the database, and
 * saying so directly is clearer than fighting an ORM into emitting it.
 *
 * <p>The overdraft rule is the {@code amount >= 0} check on the table. This code does not test the
 * balance first and then subtract: it subtracts and lets the constraint refuse, because a
 * check-then-act is two statements with a gap in the middle that a concurrent spend fits into
 * exactly.
 */
@Repository
public class WalletRepositoryAdapter implements WalletRepository {

    private final JdbcClient jdbc;

    WalletRepositoryAdapter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public List<Balance> balances(ProjectId projectId, PlayerId playerId) {
        return jdbc.sql(
                        """
                        select currency, amount, updated_at
                          from player_currency
                         where project_id = :projectId and player_id = :playerId
                         order by currency
                        """)
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .query(
                        (rs, row) ->
                                new Balance(
                                        new CurrencyCode(rs.getString("currency")),
                                        rs.getLong("amount"),
                                        rs.getTimestamp("updated_at").toInstant()))
                .list();
    }

    @Override
    @Transactional
    public Optional<Balance> adjust(
            ProjectId projectId, PlayerId playerId, CurrencyCode currency, long delta, Instant at) {

        Instant when = at.truncatedTo(ChronoUnit.MICROS);

        try {
            if (add(projectId, playerId, currency, delta, when) > 0) {
                return balanceOf(projectId, playerId, currency);
            }
        } catch (DataIntegrityViolationException refused) {
            // The overdraft check. A debit that would go below zero, refused by the constraint
            // rather than by a test-then-write with a gap in the middle.
            return Optional.empty();
        }

        // No row yet. A debit from nothing is a refusal, not a first grant.
        if (delta < 0) {
            return Optional.empty();
        }

        try {
            insert(projectId, playerId, currency, delta, when);
        } catch (DataIntegrityViolationException raced) {
            // Another thread created the row between the update and the insert. This must be a
            // retry and not a refusal: the first version of this returned empty here, and twenty
            // concurrent first grants lost two of themselves -- silently, which is exactly the
            // failure the single-statement arithmetic exists to prevent, reintroduced one layer up.
            try {
                if (add(projectId, playerId, currency, delta, when) == 0) {
                    return Optional.empty();
                }
            } catch (DataIntegrityViolationException stillRefused) {
                return Optional.empty();
            }
        }

        return balanceOf(projectId, playerId, currency);
    }

    /** The whole adjustment, as one statement. Returns how many rows it changed. */
    private int add(
            ProjectId projectId, PlayerId playerId, CurrencyCode currency, long delta, Instant when) {
        return jdbc.sql(
                        """
                        update player_currency
                           set amount = amount + :delta, updated_at = :at
                         where project_id = :projectId
                           and player_id = :playerId
                           and currency = :currency
                        """)
                .param("delta", delta)
                .param("at", java.sql.Timestamp.from(when))
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .param("currency", currency.value())
                .update();
    }

    private void insert(
            ProjectId projectId, PlayerId playerId, CurrencyCode currency, long amount, Instant when) {
        jdbc.sql(
                        """
                        insert into player_currency
                               (project_id, player_id, currency, amount, updated_at)
                        values (:projectId, :playerId, :currency, :amount, :at)
                        """)
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .param("currency", currency.value())
                .param("amount", amount)
                .param("at", java.sql.Timestamp.from(when))
                .update();
    }

    private Optional<Balance> balanceOf(ProjectId projectId, PlayerId playerId, CurrencyCode currency) {
        return jdbc.sql(
                        """
                        select currency, amount, updated_at
                          from player_currency
                         where project_id = :projectId and player_id = :playerId and currency = :currency
                        """)
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .param("currency", currency.value())
                .query(
                        (rs, row) ->
                                new Balance(
                                        new CurrencyCode(rs.getString("currency")),
                                        rs.getLong("amount"),
                                        rs.getTimestamp("updated_at").toInstant()))
                .optional();
    }
}
