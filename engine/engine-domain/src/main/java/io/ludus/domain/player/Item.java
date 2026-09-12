// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import io.ludus.domain.content.ContentBody;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.regex.Pattern;

/**
 * Something a player can own.
 *
 * <p>Reshaped deliberately. The model this comes from had an item type that assumed particular
 * effects — an enum of one game's power-ups, with the engine knowing what each of them did — so a
 * second game needed a fork. Here the engine knows an item has an id, a name, a type drawn from the
 * project's own vocabulary, an opaque sprite reference and a document of attributes it does not
 * read.
 *
 * <p>What keeps the attributes from being a junk drawer is not the engine understanding them: it is
 * that they are validated against a schema the project declares. A project that wants
 * {@code {"damage": 12}} to mean something says so, and Ludus ships knowing nothing about damage.
 *
 * <p>{@link #spriteRef()} is a reference the game resolves, not a path or a URL the engine fetches.
 * An engine that dereferenced it would be a request-forgery hole with extra steps.
 */
public record Item(
        ProjectId projectId,
        Slug id,
        String name,
        String itemType,
        String spriteRef,
        ContentBody attributes,
        Instant createdAt,
        Instant updatedAt) {

    public static final int MAX_NAME_LENGTH = 255;
    public static final int MAX_TYPE_LENGTH = 64;
    public static final int MAX_SPRITE_REF_LENGTH = 255;

    private static final Pattern TYPE_FORMAT = Pattern.compile("^[a-z0-9_]+$");

    public Item {
        if (projectId == null) {
            throw new IllegalArgumentException("an item must belong to a project");
        }
        if (id == null) {
            throw new IllegalArgumentException("item id must not be null");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("an item needs a name");
        }
        if (name.length() > MAX_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "an item name must be at most " + MAX_NAME_LENGTH + " characters");
        }
        if (itemType == null || !TYPE_FORMAT.matcher(itemType).matches()) {
            throw new IllegalArgumentException(
                    "an item type must match ^[a-z0-9_]+$, was '" + itemType + "'");
        }
        if (itemType.length() > MAX_TYPE_LENGTH) {
            throw new IllegalArgumentException(
                    "an item type must be at most " + MAX_TYPE_LENGTH + " characters");
        }
        if (spriteRef != null && spriteRef.length() > MAX_SPRITE_REF_LENGTH) {
            throw new IllegalArgumentException(
                    "a sprite reference must be at most " + MAX_SPRITE_REF_LENGTH + " characters");
        }
        if (attributes == null) {
            throw new IllegalArgumentException("an item must have an attributes document, even '{}'");
        }
        if (createdAt == null || updatedAt == null) {
            throw new IllegalArgumentException("an item must carry both of its timestamps");
        }
    }

    public static Item create(
            ProjectId projectId,
            Slug id,
            String name,
            String itemType,
            String spriteRef,
            ContentBody attributes,
            Instant now) {
        return new Item(projectId, id, name, itemType, spriteRef, attributes, now, now);
    }

    /** A replacement. Identity, project and creation time survive an edit. */
    public Item with(
            String newName,
            String newType,
            String newSpriteRef,
            ContentBody newAttributes,
            Instant now) {
        return new Item(
                projectId, id, newName, newType, newSpriteRef, newAttributes, createdAt, now);
    }

    public static boolean isValidType(String candidate) {
        return candidate != null
                && candidate.length() <= MAX_TYPE_LENGTH
                && TYPE_FORMAT.matcher(candidate).matches();
    }
}
