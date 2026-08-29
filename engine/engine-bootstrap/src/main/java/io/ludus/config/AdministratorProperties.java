// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Binds {@code ludus.security.admin.*} — {@code LUDUS_ADMIN_EMAIL} and {@code LUDUS_ADMIN_PASSWORD}.
 *
 * <p>Used once, to create the first administrator of an empty project. There is no default
 * password and there will not be one: an install that ships with a known administrator password
 * is compromised before anyone logs in, and "the operator should change it" has never been
 * sufficient.
 */
@ConfigurationProperties(prefix = "ludus.security.admin")
public class AdministratorProperties {

    private String email;
    private String password;

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    boolean isConfigured() {
        return email != null && !email.isBlank() && password != null && !password.isBlank();
    }

    @Override
    public String toString() {
        return "AdministratorProperties[email=" + email + ", password=redacted]";
    }
}
