// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.AppConfig;
import io.ludus.domain.project.ProjectId;
import java.util.Optional;

/** Storage for the one configuration document a project has. */
public interface AppConfigRepository {

    Optional<AppConfig> find(ProjectId projectId);

    AppConfig save(AppConfig config);
}
