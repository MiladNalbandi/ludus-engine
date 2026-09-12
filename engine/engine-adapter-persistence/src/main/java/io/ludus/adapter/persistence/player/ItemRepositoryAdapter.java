// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.ItemRepository;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.player.Item;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

/**
 * Items, and the project's attribute schema.
 *
 * <p>JDBC rather than JPA, for a different reason from the wallet: the attributes and the schema are
 * documents stored verbatim, and the generated {@code jsonb} column beside each one is derived from
 * the text. An entity would invite mapping the derived column, which is the path by which a document
 * gets read back through something that re-serialises it — the same mistake the wave storage design
 * exists to prevent.
 */
@Repository
public class ItemRepositoryAdapter implements ItemRepository {

    private final JdbcClient jdbc;

    ItemRepositoryAdapter(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    private static Item toItem(java.sql.ResultSet rs) throws java.sql.SQLException {
        return new Item(
                new ProjectId((java.util.UUID) rs.getObject("project_id")),
                new Slug(rs.getString("item_id")),
                rs.getString("name"),
                rs.getString("item_type"),
                rs.getString("sprite_ref"),
                new ContentBody(rs.getString("attributes_json")),
                rs.getTimestamp("created_at").toInstant(),
                rs.getTimestamp("updated_at").toInstant());
    }

    @Override
    @Transactional
    public Item save(Item item) {
        // Replaced wholesale rather than merged: an item is a small record and a partial update
        // would need a rule for what an absent field means, which is a question with no good answer.
        int updated =
                jdbc.sql(
                                """
                                update item
                                   set name = :name, item_type = :itemType, sprite_ref = :spriteRef,
                                       attributes_json = :attributes, updated_at = :updatedAt
                                 where project_id = :projectId and item_id = :itemId
                                """)
                        .param("name", item.name())
                        .param("itemType", item.itemType())
                        .param("spriteRef", item.spriteRef())
                        .param("attributes", item.attributes().json())
                        .param("updatedAt", java.sql.Timestamp.from(item.updatedAt().truncatedTo(ChronoUnit.MICROS)))
                        .param("projectId", item.projectId().value())
                        .param("itemId", item.id().value())
                        .update();

        if (updated == 0) {
            jdbc.sql(
                            """
                            insert into item (project_id, item_id, name, item_type, sprite_ref,
                                              attributes_json, created_at, updated_at)
                            values (:projectId, :itemId, :name, :itemType, :spriteRef,
                                    :attributes, :createdAt, :updatedAt)
                            """)
                    .param("projectId", item.projectId().value())
                    .param("itemId", item.id().value())
                    .param("name", item.name())
                    .param("itemType", item.itemType())
                    .param("spriteRef", item.spriteRef())
                    .param("attributes", item.attributes().json())
                    .param("createdAt", java.sql.Timestamp.from(item.createdAt().truncatedTo(ChronoUnit.MICROS)))
                    .param("updatedAt", java.sql.Timestamp.from(item.updatedAt().truncatedTo(ChronoUnit.MICROS)))
                    .update();
        }
        return find(item.projectId(), item.id()).orElseThrow();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Item> find(ProjectId projectId, Slug id) {
        return jdbc.sql(
                        """
                        select project_id, item_id, name, item_type, sprite_ref,
                               attributes_json, created_at, updated_at
                          from item
                         where project_id = :projectId and item_id = :itemId
                        """)
                .param("projectId", projectId.value())
                .param("itemId", id.value())
                .query((rs, row) -> toItem(rs))
                .optional();
    }

    @Override
    @Transactional(readOnly = true)
    public List<Item> list(ProjectId projectId) {
        return jdbc.sql(
                        """
                        select project_id, item_id, name, item_type, sprite_ref,
                               attributes_json, created_at, updated_at
                          from item
                         where project_id = :projectId
                         order by item_type, item_id
                        """)
                .param("projectId", projectId.value())
                .query((rs, row) -> toItem(rs))
                .list();
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, Slug id) {
        // Inventory rows go with it, by foreign key. Nothing is deleted here explicitly, so no
        // second delete path can be written around the cascade.
        return jdbc.sql("delete from item where project_id = :projectId and item_id = :itemId")
                        .param("projectId", projectId.value())
                        .param("itemId", id.value())
                        .update()
                > 0;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<ContentBody> attributeSchema(ProjectId projectId) {
        return jdbc.sql("select schema_json from item_schema where project_id = :projectId")
                .param("projectId", projectId.value())
                .query(String.class)
                .optional()
                .map(ContentBody::new);
    }

    @Override
    @Transactional
    public ContentBody replaceAttributeSchema(ProjectId projectId, ContentBody schema, Instant at) {
        java.sql.Timestamp when = java.sql.Timestamp.from(at.truncatedTo(ChronoUnit.MICROS));
        int updated =
                jdbc.sql(
                                """
                                update item_schema set schema_json = :schema, updated_at = :at
                                 where project_id = :projectId
                                """)
                        .param("schema", schema.json())
                        .param("at", when)
                        .param("projectId", projectId.value())
                        .update();
        if (updated == 0) {
            jdbc.sql(
                            """
                            insert into item_schema (project_id, schema_json, updated_at)
                            values (:projectId, :schema, :at)
                            """)
                    .param("projectId", projectId.value())
                    .param("schema", schema.json())
                    .param("at", when)
                    .update();
        }
        return attributeSchema(projectId).orElseThrow();
    }
}
