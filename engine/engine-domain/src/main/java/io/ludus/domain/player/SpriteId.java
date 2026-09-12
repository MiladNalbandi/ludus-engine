// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import java.util.UUID;

/**
 * The identity of a sprite, and the name its bytes are stored under.
 *
 * <p>A generated UUID rather than the uploaded filename, for the reason {@code AudioClipId} gives:
 * the filename comes from a client and would otherwise be a path the server opens. {@code ../../etc}
 * is a filename.
 */
public record SpriteId(UUID value) {

    public SpriteId {
        if (value == null) {
            throw new IllegalArgumentException("sprite id must not be null");
        }
    }

    public static SpriteId random() {
        return new SpriteId(UUID.randomUUID());
    }

    public static SpriteId of(String value) {
        return new SpriteId(UUID.fromString(value));
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
