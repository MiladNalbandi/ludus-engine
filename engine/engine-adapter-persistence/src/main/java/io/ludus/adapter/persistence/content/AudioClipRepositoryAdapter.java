// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.application.content.port.out.AudioClipRepository;
import io.ludus.domain.content.AudioClip;
import io.ludus.domain.content.AudioClipId;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class AudioClipRepositoryAdapter implements AudioClipRepository {

    private final AudioClipJpaRepository clips;

    AudioClipRepositoryAdapter(AudioClipJpaRepository clips) {
        this.clips = clips;
    }

    @Override
    @Transactional
    public AudioClip save(AudioClip clip) {
        return clips.save(AudioClipEntity.from(clip)).toDomain();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<AudioClip> find(ProjectId projectId, AudioClipId id) {
        return clips.findByProjectIdAndId(projectId.value(), id.value())
                .map(AudioClipEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public List<AudioClip> list(ProjectId projectId) {
        return clips.findByProjectIdOrderByCreatedAtDesc(projectId.value()).stream()
                .map(AudioClipEntity::toDomain)
                .toList();
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, AudioClipId id) {
        return clips.deleteByProjectIdAndId(projectId.value(), id.value()) > 0;
    }
}
