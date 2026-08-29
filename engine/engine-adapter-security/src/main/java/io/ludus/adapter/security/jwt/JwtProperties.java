// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.jwt;

import jakarta.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Binds {@code ludus.security.jwt.*}, which is {@code LUDUS_JWT_*} in a deployment.
 *
 * <p>There is no default secret, and there will not be one. A default signing secret in a public
 * repository is a working forgery tool for every install that did not change it, and the fact
 * that operators are told to change it has never been enough. The engine refuses to start instead.
 */
@ConfigurationProperties(prefix = "ludus.security.jwt")
public class JwtProperties {

    /** HS256 requires a key of at least 256 bits; anything shorter is rejected by the library. */
    static final int MINIMUM_SECRET_BYTES = 32;

    private String secret;
    private String issuer = "ludus";
    private Duration accessTokenTtl = Duration.ofMinutes(15);
    private Duration refreshTokenTtl = Duration.ofDays(30);

    @PostConstruct
    void validate() {
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException(
                    """
                    LUDUS_JWT_SECRET is not set.

                    There is no default, deliberately: a signing secret published in a public \
                    repository lets anyone forge a token for every install that kept it. Generate \
                    one and keep it out of version control:

                        openssl rand -base64 48

                    See docs/operations/configuration.md.""");
        }
        int bytes = secret.getBytes(StandardCharsets.UTF_8).length;
        if (bytes < MINIMUM_SECRET_BYTES) {
            throw new IllegalStateException(
                    "LUDUS_JWT_SECRET is "
                            + bytes
                            + " bytes; HS256 needs at least "
                            + MINIMUM_SECRET_BYTES
                            + ". Generate one with: openssl rand -base64 48");
        }
        if (accessTokenTtl == null || accessTokenTtl.isNegative() || accessTokenTtl.isZero()) {
            throw new IllegalStateException("LUDUS_JWT_ACCESS_TTL must be a positive duration");
        }
        if (refreshTokenTtl == null || refreshTokenTtl.compareTo(accessTokenTtl) <= 0) {
            throw new IllegalStateException(
                    "LUDUS_JWT_REFRESH_TTL must be longer than LUDUS_JWT_ACCESS_TTL, otherwise"
                            + " refreshing a token gains nothing");
        }
    }

    public String getSecret() {
        return secret;
    }

    public void setSecret(String secret) {
        this.secret = secret;
    }

    public String getIssuer() {
        return issuer;
    }

    public void setIssuer(String issuer) {
        this.issuer = issuer;
    }

    public Duration getAccessTokenTtl() {
        return accessTokenTtl;
    }

    public void setAccessTokenTtl(Duration accessTokenTtl) {
        this.accessTokenTtl = accessTokenTtl;
    }

    public Duration getRefreshTokenTtl() {
        return refreshTokenTtl;
    }

    public void setRefreshTokenTtl(Duration refreshTokenTtl) {
        this.refreshTokenTtl = refreshTokenTtl;
    }

    @Override
    public String toString() {
        // Bound properties get logged by diagnostics and failure analyzers. The secret does not.
        return "JwtProperties[issuer="
                + issuer
                + ", accessTokenTtl="
                + accessTokenTtl
                + ", refreshTokenTtl="
                + refreshTokenTtl
                + ", secret=redacted]";
    }
}
