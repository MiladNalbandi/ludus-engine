// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.content.ContentBody;
import io.ludus.domain.player.Item;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

/** Items, and the schema a project validates their attributes against. */
public interface ItemRepository {

    Item save(Item item);

    Optional<Item> find(ProjectId projectId, Slug id);

    List<Item> list(ProjectId projectId);

    /**
     * Removes an item, and with it every inventory row holding it.
     *
     * <p>The cascade is a foreign key. An item deleted by any route — including one written later —
     * cannot leave players holding a thing that no longer exists.
     */
    boolean delete(ProjectId projectId, Slug id);

    /** The project's item-attribute schema, or empty when it has not declared one. */
    Optional<ContentBody> attributeSchema(ProjectId projectId);

    ContentBody replaceAttributeSchema(ProjectId projectId, ContentBody schema, Instant at);
}
