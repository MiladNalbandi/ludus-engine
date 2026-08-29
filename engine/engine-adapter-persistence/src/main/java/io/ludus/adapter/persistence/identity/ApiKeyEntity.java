// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.ApiKeyId;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.project.ProjectId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Entity
@Table(name = "api_key")
class ApiKeyEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "name", nullable = false, length = ApiKey.MAX_NAME_LENGTH)
    private String name;

    @Column(name = "prefix", nullable = false, length = 16, updatable = false)
    private String prefix;

    @Column(name = "secret_digest", nullable = false, length = 64, updatable = false)
    private String secretDigest;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 16)
    private Role role;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "revoked_at")
    private Instant revokedAt;

    protected ApiKeyEntity() {
        // for JPA
    }

    static ApiKeyEntity from(ApiKey key) {
        ApiKeyEntity entity = new ApiKeyEntity();
        entity.id = key.id().value();
        entity.projectId = key.projectId().value();
        entity.name = key.name();
        entity.prefix = key.prefix();
        entity.secretDigest = key.secretDigest().value();
        entity.role = key.role();
        entity.createdAt = key.createdAt().truncatedTo(ChronoUnit.MICROS);
        entity.revokedAt =
                key.revokedAt() == null ? null : key.revokedAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    ApiKey toDomain() {
        return new ApiKey(
                new ApiKeyId(id),
                new ProjectId(projectId),
                name,
                prefix,
                new SecretDigest(secretDigest),
                role,
                createdAt,
                revokedAt);
    }
}
