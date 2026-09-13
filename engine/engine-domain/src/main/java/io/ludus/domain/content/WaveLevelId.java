// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import java.util.UUID;

/**
 * The identity of a wave level.
 *
 * <p>A UUID rather than a slug, unlike {@link Wave}. A wave's id comes out of its document and is
 * written by an author, so it is theirs to choose and theirs to type into a URL. A level is
 * assembled in an editor and has no document, so there is no authored id to honour — and a
 * generated one means renaming a level never changes a URL.
 */
public record WaveLevelId(UUID value) {

    public WaveLevelId {
        if (value == null) {
            throw new IllegalArgumentException("wave level id must not be null");
        }
    }

    public static WaveLevelId random() {
        return new WaveLevelId(UUID.randomUUID());
    }

    public static WaveLevelId of(String value) {
        return new WaveLevelId(UUID.fromString(value));
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
