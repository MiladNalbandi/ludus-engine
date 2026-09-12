// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;

/** An uploaded image, and what is known about it. The bytes live outside the database. */
public record Sprite(
        SpriteId id,
        ProjectId projectId,
        String filename,
        String contentType,
        long sizeBytes,
        Instant createdAt) {

    public static final int MAX_FILENAME_LENGTH = 255;

    public Sprite {
        if (id == null) {
            throw new IllegalArgumentException("sprite id must not be null");
        }
        if (projectId == null) {
            throw new IllegalArgumentException("a sprite must belong to a project");
        }
        if (filename == null || filename.isBlank()) {
            throw new IllegalArgumentException("a sprite needs a filename");
        }
        if (filename.length() > MAX_FILENAME_LENGTH) {
            throw new IllegalArgumentException(
                    "a filename must be at most " + MAX_FILENAME_LENGTH + " characters");
        }
        if (contentType == null || contentType.isBlank()) {
            throw new IllegalArgumentException("a sprite needs a content type");
        }
        if (sizeBytes <= 0) {
            throw new IllegalArgumentException("a sprite must have bytes, was " + sizeBytes);
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("a sprite must carry its timestamp");
        }
    }
}
