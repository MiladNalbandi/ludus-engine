// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;

/**
 * What is known about an audio clip, without any of its bytes.
 *
 * <p>The separation is the point. A wave's audio is megabytes; its metadata is a few hundred bytes.
 * Listing twenty clips to show an author a dropdown must not read twenty files, so the bytes live
 * behind {@code AudioStore} and are only ever touched when something is actually being played.
 *
 * <p>The original filename is kept because an author who uploaded {@code boss-theme-final-v3.ogg}
 * will look for that name and not for a UUID. It is a label, never a path: see {@link AudioClipId}.
 */
public record AudioClip(
        AudioClipId id,
        ProjectId projectId,
        String filename,
        String contentType,
        long sizeBytes,
        Instant createdAt) {

    public static final int MAX_FILENAME_LENGTH = 255;

    public AudioClip {
        if (id == null) {
            throw new IllegalArgumentException("audio clip id must not be null");
        }
        if (projectId == null) {
            throw new IllegalArgumentException("an audio clip must belong to a project");
        }
        if (filename == null || filename.isBlank()) {
            throw new IllegalArgumentException("audio clip filename must not be blank");
        }
        if (filename.length() > MAX_FILENAME_LENGTH) {
            throw new IllegalArgumentException(
                    "filename must be at most " + MAX_FILENAME_LENGTH + " characters");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException("audio clip content type must not be blank");
        }
        if (sizeBytes <= 0) {
            throw new IllegalArgumentException("an audio clip must have bytes, was " + sizeBytes);
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("audio clip createdAt must not be null");
        }
    }

    public static AudioClip create(
            ProjectId projectId,
            String filename,
            String contentType,
            long sizeBytes,
            Instant createdAt) {
        return new AudioClip(
                AudioClipId.random(), projectId, filename, contentType, sizeBytes, createdAt);
    }
}
