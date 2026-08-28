// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.project;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

class ProjectTest {

    private static final Slug SLUG = new Slug("default");
    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");

    @Test
    void a_created_project_carries_the_slug_name_and_time_it_was_given() {
        Project project = Project.create(SLUG, "Default", NOW);

        assertThat(project.slug()).isEqualTo(SLUG);
        assertThat(project.name()).isEqualTo("Default");
        assertThat(project.createdAt()).isEqualTo(NOW);
        assertThat(project.id()).isNotNull();
    }

    @Test
    void two_created_projects_do_not_share_an_identity() {
        assertThat(Project.create(SLUG, "Default", NOW).id())
                .isNotEqualTo(Project.create(SLUG, "Default", NOW).id());
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t", "\n"})
    void a_project_must_have_a_name(String name) {
        assertThatIllegalArgumentException()
                .isThrownBy(() -> Project.create(SLUG, name, NOW))
                .withMessageContaining("name");
    }

    @Test
    void a_name_longer_than_the_column_is_rejected_here_rather_than_by_the_database() {
        String tooLong = "x".repeat(Project.MAX_NAME_LENGTH + 1);

        assertThatIllegalArgumentException()
                .isThrownBy(() -> Project.create(SLUG, tooLong, NOW))
                .withMessageContaining(String.valueOf(Project.MAX_NAME_LENGTH));
    }

    @Test
    void a_name_of_exactly_the_maximum_length_is_allowed() {
        String atLimit = "x".repeat(Project.MAX_NAME_LENGTH);

        assertThat(Project.create(SLUG, atLimit, NOW).name()).hasSize(Project.MAX_NAME_LENGTH);
    }

    @Test
    void the_required_parts_of_a_project_cannot_be_null() {
        ProjectId id = ProjectId.random();

        assertThatIllegalArgumentException()
                .isThrownBy(() -> new Project(null, SLUG, "Default", NOW));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> new Project(id, null, "Default", NOW));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> new Project(id, SLUG, "Default", null));
    }

    @Test
    void a_project_id_wraps_a_uuid_and_refuses_to_be_absent() {
        UUID uuid = UUID.randomUUID();

        assertThat(ProjectId.of(uuid.toString()).value()).isEqualTo(uuid);
        assertThat(new ProjectId(uuid)).hasToString(uuid.toString());
        assertThatIllegalArgumentException().isThrownBy(() -> new ProjectId(null));
    }
}
