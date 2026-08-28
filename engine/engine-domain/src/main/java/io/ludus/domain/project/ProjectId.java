// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.project;

import java.util.UUID;

/**
 * The identity of a project, and the value every other table in the schema carries.
 *
 * <p>It is a type rather than a bare {@link UUID} so that a method taking a project and a user
 * cannot be called with the two arguments the wrong way round. That mistake is invisible in a
 * signature of two {@code UUID}s and produces a query that returns nothing rather than an error,
 * which is the worst kind of bug to find later.
 */
public record ProjectId(UUID value) {

    public ProjectId {
        if (value == null) {
            throw new IllegalArgumentException("project id must not be null");
        }
    }

    public static ProjectId random() {
        return new ProjectId(UUID.randomUUID());
    }

    public static ProjectId of(String value) {
        return new ProjectId(UUID.fromString(value));
    }

    @Override
    public String toString() {
        return value.toString();
    }
}
