// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.application.content.port.out.WaveRepository;
import io.ludus.domain.content.ContentHashes;
import io.ludus.domain.content.Wave;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class WaveRepositoryAdapter implements WaveRepository {

    private final WaveJpaRepository waves;

    WaveRepositoryAdapter(WaveJpaRepository waves) {
        this.waves = waves;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Wave> find(ProjectId projectId, Slug id) {
        return waves.findByProjectIdAndWaveId(projectId.value(), id.value())
                .map(WaveEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public List<Wave> list(ProjectId projectId) {
        return waves.findByProjectIdOrderByWaveOrderAsc(projectId.value()).stream()
                .map(WaveEntity::toDomain)
                .toList();
    }

    @Override
    @Transactional(readOnly = true)
    public List<Wave> listPublished(ProjectId projectId) {
        return waves.findByProjectIdAndPublishedTrueOrderByWaveOrderAsc(projectId.value()).stream()
                .map(WaveEntity::toDomain)
                .toList();
    }

    @Override
    @Transactional
    public Wave save(Wave wave) {
        return waves.save(WaveEntity.from(wave)).toDomain();
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, Slug id) {
        return waves.deleteByProjectIdAndWaveId(projectId.value(), id.value()) > 0;
    }

    @Override
    @Transactional(readOnly = true)
    public List<Integer> takenOrders(ProjectId projectId, Slug excluding) {
        return waves.takenOrders(
                projectId.value(), excluding == null ? null : excluding.value());
    }

    @Override
    @Transactional(readOnly = true)
    public List<ContentHashes.Entry> publishedCatalogue(ProjectId projectId) {
        return waves.publishedCatalogue(projectId.value()).stream()
                .map(row -> new ContentHashes.Entry((String) row[0], (Instant) row[1]))
                .toList();
    }
}
