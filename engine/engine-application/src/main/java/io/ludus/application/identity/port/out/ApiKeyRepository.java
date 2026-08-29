// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity.port.out;

import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.ApiKeyId;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;

/** Storage for API keys. */
public interface ApiKeyRepository {

    ApiKey save(ApiKey key);

    /** Finds by the digest of a presented key: one indexed equality match, no scan. */
    Optional<ApiKey> findByDigest(ProjectId projectId, SecretDigest digest);

    Optional<ApiKey> findById(ProjectId projectId, ApiKeyId id);

    List<ApiKey> listIn(ProjectId projectId);
}
