// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.PasswordHash;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Entity
@Table(name = "app_user")
class UserEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "email", nullable = false, length = EmailAddress.MAX_LENGTH)
    private String email;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    // STRING, not ORDINAL. An ordinal column means inserting a role into the middle of the enum
    // silently relabels every existing row, and the database says nothing because the numbers
    // are all still valid.
    @Enumerated(EnumType.STRING)
    @Column(name = "role", nullable = false, length = 16)
    private Role role;

    @Column(name = "enabled", nullable = false)
    private boolean enabled;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    protected UserEntity() {
        // for JPA
    }

    private UserEntity(
            UUID id,
            UUID projectId,
            String email,
            String passwordHash,
            Role role,
            boolean enabled,
            Instant createdAt) {
        this.id = id;
        this.projectId = projectId;
        this.email = email;
        this.passwordHash = passwordHash;
        this.role = role;
        this.enabled = enabled;
        this.createdAt = createdAt;
    }

    static UserEntity from(User user) {
        return new UserEntity(
                user.id().value(),
                user.projectId().value(),
                user.email().value(),
                user.passwordHash().value(),
                user.role(),
                user.enabled(),
                user.createdAt().truncatedTo(ChronoUnit.MICROS));
    }

    User toDomain() {
        return new User(
                new UserId(id),
                new ProjectId(projectId),
                new EmailAddress(email),
                new PasswordHash(passwordHash),
                role,
                enabled,
                createdAt);
    }
}
