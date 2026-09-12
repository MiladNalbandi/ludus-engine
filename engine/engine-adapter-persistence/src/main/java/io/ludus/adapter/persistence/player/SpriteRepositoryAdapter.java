// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.SpriteRepository;
import io.ludus.domain.player.Sprite;
import io.ludus.domain.player.SpriteId;
import io.ludus.domain.project.ProjectId;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class SpriteRepositoryAdapter implements SpriteRepository {

    private final JdbcClient jdbc;

    SpriteRepositoryAdapter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    private static Sprite toSprite(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new Sprite(
                new SpriteId((UUID) rs.getObject("id")),
                new ProjectId((UUID) rs.getObject("project_id")),
                rs.getString("filename"),
                rs.getString("content_type"),
                rs.getLong("size_bytes"),
                rs.getTimestamp("created_at").toInstant());
    }

    @Override
    @Transactional
    public Sprite save(Sprite sprite) {
        jdbc.sql(
                        """
                        insert into sprite (id, project_id, filename, content_type, size_bytes, created_at)
                        values (:id, :projectId, :filename, :contentType, :sizeBytes, :createdAt)
                        """)
                .param("id", sprite.id().value())
                .param("projectId", sprite.projectId().value())
                .param("filename", sprite.filename())
                .param("contentType", sprite.contentType())
                .param("sizeBytes", sprite.sizeBytes())
                .param("createdAt", java.sql.Timestamp.from(sprite.createdAt().truncatedTo(ChronoUnit.MICROS)))
                .update();
        return find(sprite.projectId(), sprite.id()).orElseThrow();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Sprite> find(ProjectId projectId, SpriteId id) {
        return jdbc.sql(
                        """
                        select id, project_id, filename, content_type, size_bytes, created_at
                          from sprite where id = :id and project_id = :projectId
                        """)
                .param("id", id.value())
                .param("projectId", projectId.value())
                .query((rs, row) -> toSprite(rs))
                .optional();
    }

    @Override
    @Transactional(readOnly = true)
    public List<Sprite> list(ProjectId projectId) {
        return jdbc.sql(
                        """
                        select id, project_id, filename, content_type, size_bytes, created_at
                          from sprite where project_id = :projectId order by created_at desc
                        """)
                .param("projectId", projectId.value())
                .query((rs, row) -> toSprite(rs))
                .list();
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, SpriteId id) {
        return jdbc.sql("delete from sprite where id = :id and project_id = :projectId")
                        .param("id", id.value())
                        .param("projectId", projectId.value())
                        .update()
                > 0;
    }
}
