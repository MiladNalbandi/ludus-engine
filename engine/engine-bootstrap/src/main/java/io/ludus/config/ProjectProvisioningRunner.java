// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.project.ProjectProvisioning;
import io.ludus.domain.project.Project;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * Provisions the default project on start, after Flyway has run and before the port is served.
 *
 * <p>A runner rather than a migration. A migration that inserts the row records that it has run
 * in {@code flyway_schema_history}, so restoring a database into a fresh deployment, or any other
 * path where the data and the history disagree, leaves the engine with no project and no
 * intention of creating one. Asking the question on every start cannot get out of step with the
 * answer.
 *
 * <p>It throws rather than logging a warning. An engine with no project cannot serve anything, so
 * starting anyway would mean accepting a port and failing every request on it, which is a worse
 * failure to diagnose than not starting.
 */
@Component
@Order(10)
public class ProjectProvisioningRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(ProjectProvisioningRunner.class);

    private final ProjectProvisioning provisioning;

    ProjectProvisioningRunner(ProjectProvisioning provisioning) {
        this.provisioning = provisioning;
    }

    @Override
    public void run(ApplicationArguments args) {
        provisioning
                .provisionDefaultProject()
                .ifPresentOrElse(
                        this::logProject,
                        () -> log.info(
                                "Tenancy mode is 'multi'; no default project was provisioned."));
    }

    private void logProject(Project project) {
        log.info("Active project '{}' ({}).", project.slug(), project.id());
    }
}
