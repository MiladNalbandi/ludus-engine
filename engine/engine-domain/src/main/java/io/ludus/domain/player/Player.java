// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;

/**
 * Someone playing, as far as the engine is concerned.
 *
 * <p>Deliberately thin. The engine holds an identifier the game already has, an optional display
 * name, and two timestamps. It holds no email address, no password and no date of birth, because
 * storing those would make every install of Ludus a processor of personal data with the deletion
 * requests and breach obligations that follow — for a game that already has an identity system, or
 * has deliberately chosen not to have one.
 *
 * <p>{@link #externalId()} is opaque. It is never parsed, split, or interpreted here, which is what
 * lets it be a device id, a platform account id, or a hash a game invented.
 */
public record Player(
        PlayerId id,
        ProjectId projectId,
        String externalId,
        String displayName,
        Instant createdAt,
        Instant lastSeenAt) {

    public static final int MAX_EXTERNAL_ID_LENGTH = 190;
    public static final int MAX_DISPLAY_NAME_LENGTH = 120;

    public Player {
        if (id == null) {
            throw new IllegalArgumentException("player id must not be null");
        }
        if (projectId == null) {
            throw new IllegalArgumentException("a player must belong to a project");
        }
        if (externalId == null || externalId.isBlank()) {
            throw new IllegalArgumentException("a player needs the game's own identifier for them");
        }
        if (externalId.length() > MAX_EXTERNAL_ID_LENGTH) {
            throw new IllegalArgumentException(
                    "the external id must be at most " + MAX_EXTERNAL_ID_LENGTH + " characters");
        }
        if (displayName != null && displayName.length() > MAX_DISPLAY_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "a display name must be at most " + MAX_DISPLAY_NAME_LENGTH + " characters");
        }
        if (createdAt == null || lastSeenAt == null) {
            throw new IllegalArgumentException("a player must carry both of its timestamps");
        }
    }

    public static Player firstSeen(
            PlayerId id, ProjectId projectId, String externalId, Instant now) {
        return new Player(id, projectId, externalId.trim(), null, now, now);
    }

    /** Stamps a new session. The only field the engine changes without being asked. */
    public Player seenAt(Instant now) {
        return new Player(id, projectId, externalId, displayName, createdAt, now);
    }

    /** A name the player chose. Blank clears it rather than storing an empty string. */
    public Player named(String newDisplayName, Instant now) {
        String trimmed = newDisplayName == null || newDisplayName.isBlank() ? null : newDisplayName.trim();
        return new Player(id, projectId, externalId, trimmed, createdAt, now);
    }
}
