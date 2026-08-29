// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import java.util.UUID;

/** The identity of a user. A type, for the same reason {@code ProjectId} is one. */
public record UserId(UUID value) {

    public UserId {
        if (value == null) {
            throw new IllegalArgumentException("user id must not be null");
        }
    }

    public static UserId random() {
        return new UserId(UUID.randomUUID());
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
