// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.project;

import io.ludus.domain.shared.Slug;
import java.time.Instant;

/**
 * The boundary everything else in the engine lives inside.
 *
 * <p>A self-hosted install has exactly one of these and will never see the concept again: the
 * slug does not appear in its URLs and nothing asks the operator to choose one. It exists anyway
 * because retrofitting a tenant column onto a schema, its foreign keys, every query and every
 * URL is one of the more expensive things a backend can be asked to do, and adding the column on
 * the first migration costs nothing.
 *
 * <p>See docs/operations/configuration.md for what {@code LUDUS_TENANCY_MODE} does with it.
 */
public record Project(ProjectId id, Slug slug, String name, Instant createdAt) {

    public static final int MAX_NAME_LENGTH = 120;

    public Project {
        if (id == null) {
            throw new IllegalArgumentException("project id must not be null");
        }
        if (slug == null) {
            throw new IllegalArgumentException("project slug must not be null");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("project name must not be blank");
        }
        if (name.length() > MAX_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "project name must be at most " + MAX_NAME_LENGTH + " characters, was "
                            + name.length());
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("project createdAt must not be null");
        }
    }

    /** A newly identified project. The caller supplies the clock; the domain does not read one. */
    public static Project create(Slug slug, String name, Instant createdAt) {
        return new Project(ProjectId.random(), slug, name, createdAt);
    }
}
