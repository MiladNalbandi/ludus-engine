// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import java.time.Instant;

/**
 * What a successful sign-in produces.
 *
 * <p>The refresh token is the only place its plaintext exists — the repository holds a hash — so
 * this record is the one chance the caller has to send it. It is not recoverable afterwards, by
 * anyone, including an administrator.
 */
public record IssuedTokens(
        String accessToken,
        Instant accessTokenExpiresAt,
        String refreshToken,
        Instant refreshTokenExpiresAt) {}
