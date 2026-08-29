// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.identity;

import io.ludus.domain.project.ProjectId;
import java.time.Instant;

/**
 * A credential a game client can carry, belonging to one project.
 *
 * <p>What is stored is a hash and a short, non-secret prefix. The prefix exists so that a
 * presented key can be looked up by one indexed equality match instead of by hashing it against
 * every row; the hash is what the presented key is actually checked against. Storing the key
 * itself would mean a database dump is a set of working credentials.
 *
 * <p>Revocation is a timestamp rather than a deletion. "This key was revoked on Tuesday" is a
 * question people ask after an incident, and a deleted row cannot answer it.
 */
public record ApiKey(
        ApiKeyId id,
        ProjectId projectId,
        String name,
        String prefix,
        SecretDigest secretDigest,
        Role role,
        Instant createdAt,
        Instant revokedAt) {

    public static final int MAX_NAME_LENGTH = 120;
    public static final int PREFIX_LENGTH = 8;

    public ApiKey {
        if (id == null) {
            throw new IllegalArgumentException("api key id must not be null");
        }
        if (projectId == null) {
            throw new IllegalArgumentException("an api key must belong to a project");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("api key name must not be blank");
        }
        if (name.length() > MAX_NAME_LENGTH) {
            throw new IllegalArgumentException(
                    "api key name must be at most " + MAX_NAME_LENGTH + " characters");
        }
        if (prefix == null || prefix.length() != PREFIX_LENGTH) {
            throw new IllegalArgumentException(
                    "api key prefix must be exactly " + PREFIX_LENGTH + " characters");
        }
        if (secretDigest == null) {
            throw new IllegalArgumentException("api key secret digest must not be null");
        }
        if (role == null) {
            throw new IllegalArgumentException("api key role must not be null");
        }
        if (createdAt == null) {
            throw new IllegalArgumentException("api key createdAt must not be null");
        }
    }

    public static ApiKey create(
            ProjectId projectId,
            String name,
            String prefix,
            SecretDigest secretDigest,
            Role role,
            Instant createdAt) {
        return new ApiKey(
                ApiKeyId.random(), projectId, name, prefix, secretDigest, role, createdAt, null);
    }

    public boolean isRevoked() {
        return revokedAt != null;
    }

    public ApiKey revokedAt(Instant when) {
        if (when == null) {
            throw new IllegalArgumentException("revocation time must not be null");
        }
        // Revoking twice keeps the first time. When it stopped working is the useful fact.
        return isRevoked()
                ? this
                : new ApiKey(id, projectId, name, prefix, secretDigest, role, createdAt, when);
    }
}
