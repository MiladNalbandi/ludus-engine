// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.project;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.project.ProjectProvisioning;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.project.Project;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

/**
 * The whole boot sequence, end to end: Flyway applies the migration, the runner provisions the
 * project, and the row is there before anything is served.
 *
 * <p>The unit test proves the use case is idempotent against a fake. This proves the wiring is
 * real — that the bean exists, that the runner is registered, and that the adapter it talks to is
 * the one backed by the shipped migration.
 */
@SpringBootTest
@ActiveProfiles("test")
class ProjectProvisioningIntegrationTest {

    private final ProjectRepository projects;
    private final ProjectProvisioning provisioning;

    ProjectProvisioningIntegrationTest(
            @Autowired ProjectRepository projects, @Autowired ProjectProvisioning provisioning) {
        this.projects = projects;
        this.provisioning = provisioning;
    }

    @Test
    void a_default_project_exists_by_the_time_the_application_has_started() {
        assertThat(projects.findBySlug(ProjectProvisioning.DEFAULT_PROJECT_SLUG))
                .as("the application runner must have provisioned it during startup")
                .isPresent();
        assertThat(projects.count()).isEqualTo(1);
    }

    @Test
    void provisioning_again_does_not_produce_a_second_project() {
        Project first =
                projects.findBySlug(ProjectProvisioning.DEFAULT_PROJECT_SLUG).orElseThrow();

        Project again = provisioning.provisionDefaultProject().orElseThrow();

        assertThat(again.id()).isEqualTo(first.id());
        assertThat(projects.count()).isEqualTo(1);
    }
}
