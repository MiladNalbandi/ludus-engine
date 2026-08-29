// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import io.ludus.application.identity.port.out.ApiKeyRepository;
import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.ApiKeyId;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class ApiKeyRepositoryAdapter implements ApiKeyRepository {

    private final ApiKeyJpaRepository keys;

    ApiKeyRepositoryAdapter(ApiKeyJpaRepository keys) {
        this.keys = keys;
    }

    @Override
    @Transactional
    public ApiKey save(ApiKey key) {
        return keys.save(ApiKeyEntity.from(key)).toDomain();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<ApiKey> findByDigest(ProjectId projectId, SecretDigest digest) {
        return keys.findByProjectIdAndSecretDigest(projectId.value(), digest.value())
                .map(ApiKeyEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<ApiKey> findById(ProjectId projectId, ApiKeyId id) {
        return keys.findByProjectIdAndId(projectId.value(), id.value()).map(ApiKeyEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public List<ApiKey> listIn(ProjectId projectId) {
        return keys.findByProjectIdOrderByCreatedAtDesc(projectId.value()).stream()
                .map(ApiKeyEntity::toDomain)
                .toList();
    }
}
