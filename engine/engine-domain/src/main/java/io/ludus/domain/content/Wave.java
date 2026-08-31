// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;

/**
 * A wave: the document, plus the handful of things the engine indexes it by.
 *
 * <p>Everything outside {@link #body()} is <em>derived from</em> the body, not stored alongside it
 * as a separate truth. The name, the order and the schema version are read out of the document
 * when it is written; they exist as fields here and as columns in the database because you cannot
 * usefully query a text column, not because they are independently editable.
 *
 * <p>The one genuine exception is {@link #published()}, which is authoritative on the column. The
 * document mirrors it so that a document read in isolation still says whether it was live, but the
 * serving routes consult the column. Publication is an act, not a property of the content.
 */
public record Wave(
        ProjectId projectId,
        Slug id,
        String name,
        int order,
        int schemaVersion,
        String schemaUri,
        boolean published,
        ContentBody body,
        Instant createdAt,
        Instant updatedAt) {

    public static final int MAX_NAME_LENGTH = 255;

    public Wave {
        if (projectId == null) {
            throw new IllegalArgumentException("a wave must belong to a project");
        }
        if (id == null) {
            throw new IllegalArgumentException("wave id must not be null");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("wave name must not be blank");
        }
        if (name.length() > MAX_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "wave name must be at most " + MAX_NAME_LENGTH + " characters");
        }
        if (order < 0) {
            throw new IllegalArgumentException("wave order must not be negative, was " + order);
        }
        if (schemaVersion < 1) {
            throw new IllegalArgumentException(
                    "schema version must be at least 1, was " + schemaVersion);
        }
        if (schemaUri == null || schemaUri.isBlank()) {
            throw new IllegalArgumentException("schema uri must not be blank");
        }
        if (body == null) {
            throw new IllegalArgumentException("a wave must have a body");
        }
        if (createdAt == null || updatedAt == null) {
            throw new IllegalArgumentException("a wave must carry both of its timestamps");
        }
    }

    /** A newly authored draft. Nothing is published by being saved. */
    public static Wave draft(
            ProjectId projectId,
            Slug id,
            String name,
            int order,
            int schemaVersion,
            String schemaUri,
            ContentBody body,
            Instant now) {
        return new Wave(
                projectId, id, name, order, schemaVersion, schemaUri, false, body, now, now);
    }

    /** A new body replacing this one. Publication state survives an edit; timestamps move. */
    public Wave withBody(
            String newName, int newOrder, int newSchemaVersion, ContentBody newBody, Instant now) {
        return new Wave(
                projectId,
                id,
                newName,
                newOrder,
                newSchemaVersion,
                schemaUri,
                published,
                newBody,
                createdAt,
                now);
    }

    public Wave published(boolean nowPublished, Instant now) {
        return nowPublished == published
                ? this
                : new Wave(
                        projectId,
                        id,
                        name,
                        order,
                        schemaVersion,
                        schemaUri,
                        nowPublished,
                        body,
                        createdAt,
                        now);
    }

    public ContentHashes.Entry catalogueEntry() {
        return new ContentHashes.Entry(id.value(), updatedAt);
    }
}
