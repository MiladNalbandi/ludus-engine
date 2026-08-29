// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Entity
@Table(name = "refresh_token")
class RefreshTokenEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Column(name = "token_digest", nullable = false, length = 64, updatable = false)
    private String tokenDigest;

    @Column(name = "issued_at", nullable = false, updatable = false)
    private Instant issuedAt;

    @Column(name = "expires_at", nullable = false, updatable = false)
    private Instant expiresAt;

    @Column(name = "revoked_at")
    private Instant revokedAt;

    protected RefreshTokenEntity() {
        // for JPA
    }

    static RefreshTokenEntity from(RefreshToken token) {
        RefreshTokenEntity entity = new RefreshTokenEntity();
        entity.id = token.id();
        entity.projectId = token.projectId().value();
        entity.userId = token.userId().value();
        entity.tokenDigest = token.tokenDigest().value();
        entity.issuedAt = token.issuedAt().truncatedTo(ChronoUnit.MICROS);
        entity.expiresAt = token.expiresAt().truncatedTo(ChronoUnit.MICROS);
        entity.revokedAt =
                token.revokedAt() == null ? null : token.revokedAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    RefreshToken toDomain() {
        return new RefreshToken(
                id,
                new ProjectId(projectId),
                new UserId(userId),
                new SecretDigest(tokenDigest),
                issuedAt,
                expiresAt,
                revokedAt);
    }
}
