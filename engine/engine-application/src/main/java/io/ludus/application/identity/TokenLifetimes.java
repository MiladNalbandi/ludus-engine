// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import java.time.Duration;

/**
 * How long each kind of token lasts.
 *
 * <p>Short access tokens and long refresh tokens are the whole bargain: an access token cannot be
 * revoked, so it should not outlive the time it would take to notice it was stolen; a refresh
 * token can be revoked, so it is allowed to last.
 */
public record TokenLifetimes(Duration accessToken, Duration refreshToken) {

    public TokenLifetimes {
        if (accessToken == null || refreshToken == null) {
            throw new IllegalArgumentException("both token lifetimes must be set");
        }
        if (accessToken.isNegative() || accessToken.isZero()) {
            throw new IllegalArgumentException("access token lifetime must be positive");
        }
        if (refreshToken.compareTo(accessToken) <= 0) {
            throw new IllegalArgumentException(
                    "the refresh token must outlive the access token, otherwise refreshing is"
                            + " pointless");
        }
    }

    public static TokenLifetimes defaults() {
        return new TokenLifetimes(Duration.ofMinutes(15), Duration.ofDays(30));
    }
}
