// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.project;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;
import static org.assertj.core.api.Assertions.assertThatIllegalStateException;

import io.ludus.domain.project.Project;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ProjectProvisioningTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");

    private final InMemoryProjectRepository projects = new InMemoryProjectRepository();
    private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);

    private ProjectProvisioning provisioning(TenancyMode mode) {
        return new ProjectProvisioning(projects, mode, clock);
    }

    @Test
    void a_single_tenant_install_gets_a_project_on_first_start() {
        Optional<Project> project = provisioning(TenancyMode.SINGLE).provisionDefaultProject();

        assertThat(project).isPresent();
        assertThat(project.get().slug()).isEqualTo(ProjectProvisioning.DEFAULT_PROJECT_SLUG);
        assertThat(project.get().createdAt()).isEqualTo(NOW);
        assertThat(projects.count()).isEqualTo(1);
    }

    @Test
    void the_second_start_finds_the_project_the_first_one_created() {
        ProjectProvisioning provisioning = provisioning(TenancyMode.SINGLE);

        Project first = provisioning.provisionDefaultProject().orElseThrow();
        Project second = provisioning.provisionDefaultProject().orElseThrow();

        assertThat(second.id()).isEqualTo(first.id());
        assertThat(projects.count())
                .as("provisioning is idempotent; it must not add a project per restart")
                .isEqualTo(1);
    }

    @Test
    void a_multi_tenant_install_provisions_nothing() {
        assertThat(provisioning(TenancyMode.MULTI).provisionDefaultProject()).isEmpty();
        assertThat(projects.count()).isZero();
    }

    /**
     * The case that makes this worth a test rather than an {@code if}: a database that already
     * holds someone else's project, pointed at by an install that thinks it owns everything.
     */
    @Test
    void a_single_tenant_install_refuses_a_database_that_already_holds_another_project() {
        projects.save(Project.create(new Slug("someone_elses_game"), "Someone else's", NOW));

        assertThatIllegalStateException()
                .isThrownBy(() -> provisioning(TenancyMode.SINGLE).provisionDefaultProject())
                .withMessageContaining("single")
                .withMessageContaining("Refusing");

        assertThat(projects.count()).isEqualTo(1);
    }

    @Test
    void the_configured_mode_is_one_of_two_values_or_the_start_fails() {
        assertThat(TenancyMode.fromConfigurationValue("single")).isEqualTo(TenancyMode.SINGLE);
        assertThat(TenancyMode.fromConfigurationValue(" MULTI ")).isEqualTo(TenancyMode.MULTI);

        assertThatIllegalArgumentException()
                .isThrownBy(() -> TenancyMode.fromConfigurationValue("sngle"))
                .withMessageContaining("sngle");
        assertThatIllegalArgumentException()
                .isThrownBy(() -> TenancyMode.fromConfigurationValue("  "));
    }
}
