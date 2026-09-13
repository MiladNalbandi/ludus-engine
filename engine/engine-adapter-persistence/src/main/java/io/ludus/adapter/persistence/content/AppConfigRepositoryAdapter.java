// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import io.ludus.application.content.port.out.AppConfigRepository;
import io.ludus.domain.content.AppConfig;
import io.ludus.domain.project.ProjectId;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class AppConfigRepositoryAdapter implements AppConfigRepository {

    private final AppConfigJpaRepository configs;

    AppConfigRepositoryAdapter(AppConfigJpaRepository configs) {
        this.configs = configs;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<AppConfig> find(ProjectId projectId) {
        return configs.findById(projectId.value()).map(AppConfigEntity::toDomain);
    }

    @Override
    @Transactional
    public AppConfig save(AppConfig config) {
        // The project id is the key, so a second save replaces rather than adds. That is the
        // schema's guarantee that configuration is singular, not this method's.
        return configs.save(AppConfigEntity.from(config)).toDomain();
    }
}
