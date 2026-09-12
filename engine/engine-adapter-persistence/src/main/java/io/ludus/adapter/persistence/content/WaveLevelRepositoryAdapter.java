// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.application.content.port.out.WaveLevelRepository;
import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class WaveLevelRepositoryAdapter implements WaveLevelRepository {

    private final WaveLevelJpaRepository levels;
    private final WaveLevelWaveJpaRepository memberships;
    private final WaveLevelActivationJpaRepository activations;

    WaveLevelRepositoryAdapter(
            WaveLevelJpaRepository levels,
            WaveLevelWaveJpaRepository memberships,
            WaveLevelActivationJpaRepository activations) {
        this.levels = levels;
        this.memberships = memberships;
        this.activations = activations;
    }

    @Override
    @Transactional
    public WaveLevel save(WaveLevel level) {
        WaveLevelEntity saved = levels.save(WaveLevelEntity.from(level));

        // Replaced wholesale rather than diffed. A diff has to reorder rows in place, and an
        // in-place reorder collides with the (level, wave) key halfway through — which is exactly
        // what went wrong when Hibernate was managing this as an ordered collection.
        memberships.deleteMembershipsOf(saved.id());
        List<WaveLevelWaveEntity> rows = new ArrayList<>();
        List<Slug> waves = level.waves();
        for (int position = 0; position < waves.size(); position++) {
            rows.add(
                    WaveLevelWaveEntity.of(
                            saved.id(),
                            saved.projectId(),
                            waves.get(position).value(),
                            position));
        }
        memberships.saveAll(rows);

        return saved.toDomain(waves);
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<WaveLevel> find(ProjectId projectId, WaveLevelId id) {
        return levels.findByIdAndProjectId(id.value(), projectId.value()).map(this::withMembers);
    }

    @Override
    @Transactional(readOnly = true)
    public List<WaveLevel> list(ProjectId projectId) {
        return levels.findByProjectIdOrderByNameAsc(projectId.value()).stream()
                .map(this::withMembers)
                .toList();
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, WaveLevelId id) {
        // The membership rows and the activation row go with it, by foreign key. Nothing is
        // deleted here explicitly, on purpose: a cascade written as statements is one somebody can
        // add a second delete path around.
        return levels.deleteByIdAndProjectId(id.value(), projectId.value()) > 0;
    }

    @Override
    @Transactional
    public void activate(ProjectId projectId, WaveLevelId id, Instant at) {
        // A save onto a primary key that is the project id. Whatever was active is overwritten in
        // the same statement, so there is no moment with two active levels and none with zero.
        activations.save(WaveLevelActivationEntity.of(projectId.value(), id.value(), at));
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<WaveLevel> findActive(ProjectId projectId) {
        return activations
                .findById(projectId.value())
                .flatMap(
                        activation ->
                                levels.findByIdAndProjectId(
                                        activation.waveLevelId(), projectId.value()))
                .map(this::withMembers);
    }

    private WaveLevel withMembers(WaveLevelEntity entity) {
        return entity.toDomain(
                memberships.findByWaveLevelIdOrderByPositionAsc(entity.id()).stream()
                        .map(row -> new Slug(row.waveId()))
                        .toList());
    }
}
