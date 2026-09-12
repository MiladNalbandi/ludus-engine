// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import java.util.UUID;

/**
 * The identity of an audio clip, and the name its bytes are stored under.
 *
 * <p>A generated UUID rather than the uploaded filename, which matters for more than tidiness: the
 * filename comes from a client and would otherwise be a path the server opens. {@code ../../etc}
 * is a filename. A UUID cannot traverse anything.
 */
public record AudioClipId(UUID value) {

    public AudioClipId {
        if (value == null) {
            throw new IllegalArgumentException("audio clip id must not be null");
        }
    }

    public static AudioClipId random() {
        return new AudioClipId(UUID.randomUUID());
    }

    public static AudioClipId of(String value) {
        return new AudioClipId(UUID.fromString(value));
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
