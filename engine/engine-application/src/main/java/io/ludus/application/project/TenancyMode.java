// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project;

/**
 * How many projects this installation is allowed to hold.
 *
 * <p>The distinction is about provisioning and routing, not about storage: the schema is the same
 * either way, because every table carries a project identifier from the first migration.
 */
public enum TenancyMode {

    /**
     * One project, created on first start and never chosen by anyone. What a self-hosted install
     * wants: nothing in the interface mentions projects at all.
     */
    SINGLE,

    /**
     * Several projects, created and selected explicitly. The hosted deployment — {@code v2.0.0},
     * <a href="https://github.com/MiladNalbandi/ludus-engine/issues/17">#17</a>. Nothing routes to
     * it yet; the value exists so that configuration can already say which world it is in.
     */
    MULTI;

    public static TenancyMode fromConfigurationValue(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("tenancy mode must not be blank");
        }
        return switch (value.trim().toLowerCase()) {
            case "single" -> SINGLE;
            case "multi" -> MULTI;
            default -> throw new IllegalArgumentException(
                    "unknown tenancy mode '" + value + "', expected 'single' or 'multi'");
        };
    }
}
