// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.ProgressRepository;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.player.XpStage;
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
 * XP, and the project's curve.
 *
 * <p>JDBC for the same reason as balances: XP is accumulated by many small additions, and a
 * read-modify-write loses them under concurrency. There is deliberately no stored stage — it is
 * derived from the XP and the curve, so editing the curve does not leave every player's stage
 * stale in a column nobody thought to recompute.
 */
@Repository
public class ProgressRepositoryAdapter implements ProgressRepository {

    private final JdbcClient jdbc;

    ProgressRepositoryAdapter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    @Transactional(readOnly = true)
    public long xp(ProjectId projectId, PlayerId playerId) {
        // Zero rather than empty for a player who has never earned any: everyone has a total, and
        // a caller that had to handle "no row" would render an empty progress bar as an error.
        return jdbc.sql(
                        "select xp from player_progress where project_id = :projectId and player_id = :playerId")
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .query(Long.class)
                .optional()
                .orElse(0L);
    }

    @Override
    @Transactional
    public Optional<Long> addXp(ProjectId projectId, PlayerId playerId, long delta, Instant at) {
        Instant when = at.truncatedTo(ChronoUnit.MICROS);

        try {
            if (add(projectId, playerId, delta, when) > 0) {
                return Optional.of(xp(projectId, playerId));
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
                            insert into player_progress (project_id, player_id, xp, updated_at)
                            values (:projectId, :playerId, :xp, :at)
                            """)
                    .param("projectId", projectId.value())
                    .param("playerId", playerId.value())
                    .param("xp", delta)
                    .param("at", java.sql.Timestamp.from(when))
                    .update();
        } catch (DataIntegrityViolationException raced) {
            // Another thread created the row first. A retry, not a refusal -- see
            // WalletRepositoryAdapter for the failure this avoids.
            try {
                if (add(projectId, playerId, delta, when) == 0) {
                    return Optional.empty();
                }
            } catch (DataIntegrityViolationException stillRefused) {
                return Optional.empty();
            }
        }

        return Optional.of(xp(projectId, playerId));
    }

    private int add(ProjectId projectId, PlayerId playerId, long delta, Instant when) {
        return jdbc.sql(
                        """
                        update player_progress
                           set xp = xp + :delta, updated_at = :at
                         where project_id = :projectId and player_id = :playerId
                        """)
                .param("delta", delta)
                .param("at", java.sql.Timestamp.from(when))
                .param("projectId", projectId.value())
                .param("playerId", playerId.value())
                .update();
    }

    @Override
    @Transactional(readOnly = true)
    public List<XpStage> curve(ProjectId projectId) {
        return jdbc.sql(
                        """
                        select stage, xp_required, label
                          from xp_stage
                         where project_id = :projectId
                         order by xp_required
                        """)
                .param("projectId", projectId.value())
                .query(
                        (rs, row) ->
                                new XpStage(
                                        rs.getInt("stage"),
                                        rs.getLong("xp_required"),
                                        rs.getString("label")))
                .list();
    }

    @Override
    @Transactional
    public List<XpStage> replaceCurve(ProjectId projectId, List<XpStage> stages) {
        // Deleted and reinserted in one transaction. Diffing would have to reorder thresholds in
        // place, and the unique index on them refuses an intermediate state -- the same collision
        // the wave-level memberships ran into.
        jdbc.sql("delete from xp_stage where project_id = :projectId")
                .param("projectId", projectId.value())
                .update();

        for (XpStage stage : stages) {
            jdbc.sql(
                            """
                            insert into xp_stage (project_id, stage, xp_required, label)
                            values (:projectId, :stage, :xpRequired, :label)
                            """)
                    .param("projectId", projectId.value())
                    .param("stage", stage.stage())
                    .param("xpRequired", stage.xpRequired())
                    .param("label", stage.label())
                    .update();
        }
        return curve(projectId);
    }
}
