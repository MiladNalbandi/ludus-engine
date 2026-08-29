// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class RefreshTokenRepositoryAdapter implements RefreshTokenRepository {

    private final RefreshTokenJpaRepository tokens;

    RefreshTokenRepositoryAdapter(RefreshTokenJpaRepository tokens) {
        this.tokens = tokens;
    }

    @Override
    @Transactional
    public RefreshToken save(RefreshToken token) {
        return tokens.save(RefreshTokenEntity.from(token)).toDomain();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<RefreshToken> findByDigest(ProjectId projectId, SecretDigest digest) {
        return tokens.findByProjectIdAndTokenDigest(projectId.value(), digest.value())
                .map(RefreshTokenEntity::toDomain);
    }

    @Override
    @Transactional
    public int revokeAllFor(ProjectId projectId, UserId userId, Instant when) {
        return tokens.revokeAllFor(projectId.value(), userId.value(), when);
    }
}
