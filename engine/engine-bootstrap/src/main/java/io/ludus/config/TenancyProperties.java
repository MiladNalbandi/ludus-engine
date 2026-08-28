// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.project.TenancyMode;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Binds {@code ludus.tenancy.*}, which is {@code LUDUS_TENANCY_MODE} in a deployment.
 *
 * <p>The string is turned into a {@link TenancyMode} here rather than in the application layer,
 * because parsing configuration is an adapter concern and the application should receive a value
 * that is already known to be one of two things.
 */
@ConfigurationProperties(prefix = "ludus.tenancy")
public class TenancyProperties {

    private String mode = "single";

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    /**
     * @throws IllegalArgumentException if the configured value is neither {@code single} nor
     *     {@code multi}, which fails the start rather than silently defaulting. A typo in this
     *     setting is not a thing to guess at.
     */
    public TenancyMode resolved() {
        return TenancyMode.fromConfigurationValue(mode);
    }
}
