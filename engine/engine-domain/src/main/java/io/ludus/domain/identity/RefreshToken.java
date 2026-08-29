// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.UUID;

/**
 * A long-lived credential that can be exchanged for a new access token.
 *
 * <p>Access tokens are short-lived and not stored, which is the point of them: verifying one is
 * a signature check and nothing else. That also means they cannot be revoked. Refresh tokens are
 * the other half of the trade — they live in the database precisely so that signing someone out
 * is a row update rather than a wait.
 *
 * <p>Only the hash is kept, for the same reason as an API key: a database dump should not be a
 * set of working sessions.
 */
public record RefreshToken(
        UUID id,
        ProjectId projectId,
        UserId userId,
        SecretDigest tokenDigest,
        Instant issuedAt,
        Instant expiresAt,
        Instant revokedAt) {

    public RefreshToken {
        if (id == null || projectId == null || userId == null || tokenDigest == null) {
            throw new IllegalArgumentException("refresh token is missing a required field");
        }
        if (issuedAt == null || expiresAt == null) {
            throw new IllegalArgumentException("refresh token must have both of its times");
        }
        if (!expiresAt.isAfter(issuedAt)) {
            throw new IllegalArgumentException("a refresh token must expire after it was issued");
        }
    }

    public static RefreshToken issue(
            ProjectId projectId,
            UserId userId,
            SecretDigest tokenDigest,
            Instant issuedAt,
            Instant expiresAt) {
        return new RefreshToken(
                UUID.randomUUID(), projectId, userId, tokenDigest, issuedAt, expiresAt, null);
    }

    public boolean isUsableAt(Instant when) {
        return revokedAt == null && when.isBefore(expiresAt);
    }

    public RefreshToken revokedAt(Instant when) {
        return revokedAt != null
                ? this
                : new RefreshToken(id, projectId, userId, tokenDigest, issuedAt, expiresAt, when);
    }
}
