// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content;

import io.ludus.application.content.port.out.WaveLevelRepository;
import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.domain.content.Wave;
import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Assembling waves into levels, and choosing which level a game is playing.
 *
 * <p>A level is a sequence, not a set: the order is what the player experiences, and it is the list
 * order rather than a number anybody types.
 */
public class WaveLevels {

    private final WaveLevelRepository levels;
    private final WaveRepository waves;
    private final Clock clock;

    public WaveLevels(WaveLevelRepository levels, WaveRepository waves, Clock clock) {
        this.levels = levels;
        this.waves = waves;
        this.clock = clock;
    }

    public WaveLevel create(ProjectId projectId, String name, String description, List<Slug> waveIds) {
        requireEveryWaveExists(projectId, waveIds);
        return levels.save(
                WaveLevel.create(
                        WaveLevelId.random(),
                        projectId,
                        requireName(name),
                        description,
                        waveIds,
                        clock.instant()));
    }

    /** Renames or resequences a level. Missing, for this project, is empty rather than an error. */
    public Optional<WaveLevel> update(
            ProjectId projectId,
            WaveLevelId id,
            String name,
            String description,
            List<Slug> waveIds) {
        return levels.find(projectId, id)
                .map(
                        existing -> {
                            requireEveryWaveExists(projectId, waveIds);
                            return levels.save(
                                    existing.with(
                                            requireName(name),
                                            description,
                                            waveIds,
                                            clock.instant()));
                        });
    }

    public List<WaveLevel> list(ProjectId projectId) {
        return levels.list(projectId);
    }

    public Optional<WaveLevel> find(ProjectId projectId, WaveLevelId id) {
        return levels.find(projectId, id);
    }

    public boolean delete(ProjectId projectId, WaveLevelId id) {
        return levels.delete(projectId, id);
    }

    /**
     * Makes a level the active one.
     *
     * <p>The existence check is here so that activating something that is not there is a {@code
     * 404} rather than a foreign key violation surfacing as a {@code 500}. The constraint is still
     * in the database, and is what actually guarantees there is never more than one.
     */
    public boolean activate(ProjectId projectId, WaveLevelId id) {
        if (levels.find(projectId, id).isEmpty()) {
            return false;
        }
        levels.activate(projectId, id, clock.instant());
        return true;
    }

    public Optional<WaveLevel> active(ProjectId projectId) {
        return levels.findActive(projectId);
    }

    /**
     * The active level as a game client sees it: its published waves, in order.
     *
     * <p>Unpublished members are dropped rather than served, because a level is assembled while its
     * waves are still being written and publication is what says a wave is ready. Dropping them is
     * the only option that does not either leak drafts or block an editor from building a level in
     * advance.
     *
     * <p>That the two views differ is deliberate, and the reason the authoring response marks each
     * member's publication state: an editor who cannot see which entries players are not getting
     * finds out from a player.
     */
    public Optional<PlayableLevel> activeForPlayers(ProjectId projectId) {
        return levels.findActive(projectId)
                .map(
                        level -> {
                            List<Wave> published = new ArrayList<>();
                            for (Slug waveId : level.waves()) {
                                waves.findPublished(projectId, waveId).ifPresent(published::add);
                            }
                            return new PlayableLevel(level, List.copyOf(published));
                        });
    }

    private String requireName(String name) {
        if (name == null || name.isBlank()) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/name", "a level needs a name")));
        }
        return name;
    }

    /**
     * Every listed wave must exist, in this project.
     *
     * <p>The database refuses a membership row pointing at a wave that is not there, and would do
     * so for one in another project too. This runs first so the author gets every bad entry at once
     * with the index that produced it, rather than a constraint name.
     */
    private void requireEveryWaveExists(ProjectId projectId, List<Slug> waveIds) {
        if (waveIds == null) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/waves", "a level needs its list of waves, even an empty one")));
        }
        List<ContentViolation> missing = new ArrayList<>();
        for (int i = 0; i < waveIds.size(); i++) {
            Slug waveId = waveIds.get(i);
            if (waveId == null || waves.find(projectId, waveId).isEmpty()) {
                missing.add(
                        new ContentViolation(
                                "/waves/" + i,
                                "no wave '" + waveId + "' in this project"));
            }
        }
        if (!missing.isEmpty()) {
            throw new ContentRejected(missing);
        }
    }

    /** An active level and the waves a client may actually play, already filtered and ordered. */
    public record PlayableLevel(WaveLevel level, List<Wave> waves) {}
}
