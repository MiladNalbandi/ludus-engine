// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.config;

import io.ludus.application.identity.AdministratorSeeding;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.identity.User;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

/**
 * Creates the first administrator on start, if one is configured and the project is empty.
 *
 * <p>Ordered after {@link ProjectProvisioningRunner}, because there has to be a project to put a
 * user in. That ordering is declared rather than assumed: two runners with no stated order run in
 * whatever order the context hands them over, which works until it does not.
 *
 * <p>Starting without an administrator configured is allowed and merely logged. It is a real
 * situation — an install whose administrator was created on a previous run — and refusing would
 * mean every restart needs the password on hand.
 */
@Component
@Order(20)
public class AdministratorSeedingRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(AdministratorSeedingRunner.class);

    private final AdministratorSeeding seeding;
    private final ActiveProject activeProject;
    private final AdministratorProperties properties;

    AdministratorSeedingRunner(
            AdministratorSeeding seeding,
            ActiveProject activeProject,
            AdministratorProperties properties) {
        this.seeding = seeding;
        this.activeProject = activeProject;
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!properties.isConfigured()) {
            log.info(
                    "No administrator configured (LUDUS_ADMIN_EMAIL / LUDUS_ADMIN_PASSWORD)."
                            + " Nothing was seeded; if this project has no users, nobody can"
                            + " sign in.");
            return;
        }

        seeding.seed(activeProject.id(), properties.getEmail(), properties.getPassword())
                .ifPresentOrElse(
                        this::logSeeded,
                        () ->
                                log.info(
                                        "Project already has users; the configured administrator"
                                                + " was not seeded and no password was changed."));
    }

    private void logSeeded(User admin) {
        log.info("Seeded the first administrator, {} ({}).", admin.email(), admin.id());
    }
}
