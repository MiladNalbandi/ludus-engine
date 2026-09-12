// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.domain.content.AudioClip;
import io.ludus.domain.content.AudioClipId;
import io.ludus.domain.project.ProjectId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Entity
@Table(name = "audio_clip")
class AudioClipEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "filename", nullable = false, length = AudioClip.MAX_FILENAME_LENGTH)
    private String filename;

    @Column(name = "content_type", nullable = false, length = 128)
    private String contentType;

    @Column(name = "size_bytes", nullable = false)
    private long sizeBytes;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected AudioClipEntity() {
        // for JPA
    }

    static AudioClipEntity from(AudioClip clip) {
        AudioClipEntity entity = new AudioClipEntity();
        entity.id = clip.id().value();
        entity.projectId = clip.projectId().value();
        entity.filename = clip.filename();
        entity.contentType = clip.contentType();
        entity.sizeBytes = clip.sizeBytes();
        entity.createdAt = clip.createdAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    AudioClip toDomain() {
        return new AudioClip(
                new AudioClipId(id),
                new ProjectId(projectId),
                filename,
                contentType,
                sizeBytes,
                createdAt);
    }
}
