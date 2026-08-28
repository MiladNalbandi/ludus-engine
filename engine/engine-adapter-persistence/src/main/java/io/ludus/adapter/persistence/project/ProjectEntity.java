// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.project;

import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

/**
 * The stored shape of a project. Deliberately not the domain type.
 *
 * <p>{@link Project} is a record with a validating constructor; JPA wants a mutable class with a
 * no-arg constructor and setters for the fields it hydrates. Making the domain type satisfy that
 * would mean giving up the constructor that makes an invalid project unrepresentable, in exchange
 * for saving one mapper. The mapper is the cheaper of the two.
 */
@Entity
@Table(name = "project")
class ProjectEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "slug", nullable = false, length = Slug.MAX_LENGTH, updatable = false)
    private String slug;

    @Column(name = "name", nullable = false, length = Project.MAX_NAME_LENGTH)
    private String name;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected ProjectEntity() {
        // for JPA
    }

    private ProjectEntity(UUID id, String slug, String name, Instant createdAt) {
        this.id = id;
        this.slug = slug;
        this.name = name;
        this.createdAt = createdAt;
    }

    static ProjectEntity from(Project project) {
        return new ProjectEntity(
                project.id().value(),
                project.slug().value(),
                project.name(),
                // PostgreSQL stores timestamps to microsecond precision and Instant carries
                // nanoseconds, so a value written and read back is not equal to the one handed
                // in. Truncating here means the object this adapter returns is the object the
                // database holds, rather than one that will differ after the next restart.
                project.createdAt().truncatedTo(ChronoUnit.MICROS));
    }

    Project toDomain() {
        return new Project(new ProjectId(id), new Slug(slug), name, createdAt);
    }
}
