// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.Optional;

/** Storage for refresh tokens, which exist so that signing out is immediate. */
public interface RefreshTokenRepository {

    RefreshToken save(RefreshToken token);

    /**
     * Finds a token by the digest of its presented value. Scoped to a project, like everything
     * else, so a token cannot be redeemed against a project it was not issued for.
     */
    Optional<RefreshToken> findByDigest(ProjectId projectId, SecretDigest digest);

    /** Revokes every token belonging to one user. What "sign out everywhere" is. */
    int revokeAllFor(ProjectId projectId, UserId userId, Instant when);
}
