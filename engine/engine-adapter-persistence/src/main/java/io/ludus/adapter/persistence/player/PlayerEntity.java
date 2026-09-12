// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

@Entity
@Table(name = "player")
class PlayerEntity {

    @Id
    @Column(name = "id", nullable = false, updatable = false)
    private UUID id;

    @Column(name = "project_id", nullable = false, updatable = false)
    private UUID projectId;

    @Column(name = "external_id", nullable = false, length = Player.MAX_EXTERNAL_ID_LENGTH, updatable = false)
    private String externalId;

    @Column(name = "display_name", length = Player.MAX_DISPLAY_NAME_LENGTH)
    private String displayName;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "last_seen_at", nullable = false)
    private Instant lastSeenAt;

    protected PlayerEntity() {
        // for JPA
    }

    static PlayerEntity from(Player player) {
        PlayerEntity entity = new PlayerEntity();
        entity.id = player.id().value();
        entity.projectId = player.projectId().value();
        entity.externalId = player.externalId();
        entity.displayName = player.displayName();
        // Truncated to microseconds, as everywhere else: PostgreSQL keeps microseconds and the JVM
        // offers nanoseconds, so a value written and read back would otherwise differ.
        entity.createdAt = player.createdAt().truncatedTo(ChronoUnit.MICROS);
        entity.lastSeenAt = player.lastSeenAt().truncatedTo(ChronoUnit.MICROS);
        return entity;
    }

    Player toDomain() {
        return new Player(
                new PlayerId(id),
                new ProjectId(projectId),
                externalId,
                displayName,
                createdAt,
                lastSeenAt);
    }
}
