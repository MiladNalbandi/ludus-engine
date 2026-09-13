// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** Storage for wave levels, and for which one of them a project is currently playing. */
public interface WaveLevelRepository {

    WaveLevel save(WaveLevel level);

    Optional<WaveLevel> find(ProjectId projectId, WaveLevelId id);

    List<WaveLevel> list(ProjectId projectId);

    /**
     * Removes a level. Its membership rows and its activation, if it had one, go with it.
     *
     * <p>Both cascades are foreign keys rather than statements issued here, so a level deleted by
     * any route — including one written later, or by hand — cannot leave either behind.
     */
    boolean delete(ProjectId projectId, WaveLevelId id);

    /**
     * Makes this level the project's active one, replacing whatever was active before.
     *
     * <p>One call rather than deactivate-then-activate, because two statements leave a window with
     * no active level, and a client polling during that window is told the game has no content.
     *
     * <p>The instant is passed in rather than read from a clock here. Every other adapter in this
     * codebase is given its timestamps by the use case that called it, so that what a test asserts
     * about time is fixed by the test rather than by whatever the machine's clock said.
     */
    void activate(ProjectId projectId, WaveLevelId id, Instant at);

    /** Whichever level is active, or empty if the project has none. */
    Optional<WaveLevel> findActive(ProjectId projectId);
}
