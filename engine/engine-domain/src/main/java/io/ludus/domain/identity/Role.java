// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

/**
 * What a caller is allowed to do, as a closed set.
 *
 * <p>An enum rather than a string, and rather than a collection of granted permissions. Three
 * roles is enough to express every decision this engine currently makes, and a permission system
 * built before there is a decision it cannot express is a permission system designed against
 * imagined requirements. Widening this later is a migration; narrowing a free-form permission
 * model later is a rewrite.
 *
 * <p>The order is significant: each role can do everything the ones below it can.
 */
public enum Role {

    /** Reads published content. What a game client gets, and the least any caller can have. */
    VIEWER,

    /** Authors content: creates, edits and publishes. Cannot manage users or keys. */
    EDITOR,

    /** Everything, including issuing and revoking API keys. */
    ADMIN;

    /** True if this role includes everything {@code other} can do. */
    public boolean includes(Role other) {
        return this.ordinal() >= other.ordinal();
    }

    public static Role fromString(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("role must not be blank");
        }
        return switch (value.trim().toUpperCase()) {
            case "VIEWER" -> VIEWER;
            case "EDITOR" -> EDITOR;
            case "ADMIN" -> ADMIN;
            default -> throw new IllegalArgumentException(
                    "unknown role '" + value + "', expected one of VIEWER, EDITOR, ADMIN");
        };
    }
}
