// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.WaveLevels;
import io.ludus.domain.content.WaveLevel;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;
import java.util.Set;

final class WaveLevelDtos {

    private WaveLevelDtos() {}

    /** What an author sends. The id is assigned by the engine; the order is the list order. */
    @Schema(name = "WaveLevelRequest", description = "A level's name and the waves it sequences, in play order.")
        record Request(String name, String description, List<String> waves) {}

    /**
     * A level as an editor sees it.
     *
     * <p>Each member carries whether it is published, because the public route serves only the
     * published ones. An editor who cannot see which entries players will not receive finds that
     * out from a player.
     */
    @Schema(name = "WaveLevelSummary", description = "A level, its waves, and which of them players can actually reach.")
        record Summary(
            String id,
            String name,
            String description,
            boolean active,
            List<Member> waves,
            Instant createdAt,
            Instant updatedAt) {

        static Summary of(WaveLevel level, boolean active, Set<String> publishedWaveIds) {
            return new Summary(
                    level.id().toString(),
                    level.name(),
                    level.description(),
                    active,
                    level.waves().stream()
                            .map(
                                    wave ->
                                            new Member(
                                                    wave.value(),
                                                    publishedWaveIds.contains(wave.value())))
                            .toList(),
                    level.createdAt(),
                    level.updatedAt());
        }
    }

    @Schema(name = "WaveLevelMember", description = "One wave's place in a level, and whether players will receive it.")
        record Member(String waveId, boolean published) {}

    /**
     * The active level as a game client sees it: published waves only, already in order.
     *
     * <p>Summaries rather than documents. A client fetches the documents it does not already have
     * from the raw route, which is where the per-document ETags are.
     */
    @Schema(name = "PlayableWaveLevel", description = "The level currently being played, and its published waves in order.")
        record Playable(String id, String name, List<WaveDtos.Summary> waves) {

        static Playable of(WaveLevels.PlayableLevel playable) {
            return new Playable(
                    playable.level().id().toString(),
                    playable.level().name(),
                    playable.waves().stream().map(WaveDtos.Summary::of).toList());
        }
    }
}
