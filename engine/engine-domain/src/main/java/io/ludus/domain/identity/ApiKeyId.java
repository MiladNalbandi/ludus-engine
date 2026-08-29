// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import java.util.UUID;

/** The identity of an API key. Not the key itself, and safe to log. */
public record ApiKeyId(UUID value) {

    public ApiKeyId {
        if (value == null) {
            throw new IllegalArgumentException("api key id must not be null");
        }
    }

    public static ApiKeyId random() {
        return new ApiKeyId(UUID.randomUUID());
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
