// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.PlayerId;
import io.ludus.domain.player.XpStage;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.List;

/** A player's XP, and the project's curve. */
public interface ProgressRepository {

    /** Zero for a player who has never earned any, rather than empty: everyone has an XP total. */
    long xp(ProjectId projectId, PlayerId playerId);

    /**
     * Adds XP, in one statement for the same reason as a balance.
     *
     * @return the total afterwards, or empty when the change was refused for taking it below zero
     */
    java.util.Optional<Long> addXp(
            ProjectId projectId, PlayerId playerId, long delta, Instant at);

    /** The project's curve, in ascending threshold order. Empty when it has not defined one. */
    List<XpStage> curve(ProjectId projectId);

    /** Replaces the curve wholesale. Editing one stage in isolation cannot keep it consistent. */
    List<XpStage> replaceCurve(ProjectId projectId, List<XpStage> stages);
}
