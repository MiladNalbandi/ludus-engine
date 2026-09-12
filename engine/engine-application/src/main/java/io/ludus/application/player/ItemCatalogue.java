// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.content.port.out.UnitOfWork;
import io.ludus.application.player.port.out.InventoryRepository;
import io.ludus.application.player.port.out.ItemRepository;
import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.SchemaValidator;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.player.InventoryEntry;
import io.ludus.domain.player.Item;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Items a project defines, and what players hold of them.
 *
 * <p>Item attributes are validated against a schema the <em>project</em> owns. That is the whole
 * design: the engine does not know what an item's attributes mean, so it cannot check them itself,
 * and without a schema the field is a junk drawer that every client has to defend against. With one,
 * a project declares its own shape and the engine enforces it — knowing nothing about damage.
 *
 * <p>A project with no schema validates nothing, deliberately. A game that has not yet decided what
 * its items look like should not be prevented from creating one.
 */
public class ItemCatalogue {

    private final ItemRepository items;
    private final InventoryRepository inventory;
    private final PlayerRepository players;
    private final SchemaValidator schemas;
    private final UnitOfWork unitOfWork;
    private final Clock clock;

    public ItemCatalogue(
            ItemRepository items,
            InventoryRepository inventory,
            PlayerRepository players,
            SchemaValidator schemas,
            UnitOfWork unitOfWork,
            Clock clock) {
        this.items = items;
        this.inventory = inventory;
        this.players = players;
        this.schemas = schemas;
        this.unitOfWork = unitOfWork;
        this.clock = clock;
    }

    public List<Item> list(ProjectId projectId) {
        return items.list(projectId);
    }

    public Optional<Item> find(ProjectId projectId, Slug id) {
        return items.find(projectId, id);
    }

    /** Creates or replaces an item, after checking its attributes against the project's schema. */
    public Item save(
            ProjectId projectId,
            Slug id,
            String name,
            String itemType,
            String spriteRef,
            ContentBody attributes) {

        List<ContentViolation> violations = new ArrayList<>();
        if (name == null || name.isBlank()) {
            violations.add(new ContentViolation("/name", "an item needs a name"));
        }
        if (!Item.isValidType(itemType)) {
            violations.add(
                    new ContentViolation(
                            "/itemType",
                            "'" + itemType + "' is not an item type; expected ^[a-z0-9_]+$"));
        }
        if (!violations.isEmpty()) {
            throw new ContentRejected(violations);
        }

        ContentBody document = attributes == null ? new ContentBody("{}") : attributes;
        validateAttributes(projectId, document);

        Instant now = clock.instant();
        Item existing = items.find(projectId, id).orElse(null);
        Item item =
                existing == null
                        ? Item.create(projectId, id, name, itemType, spriteRef, document, now)
                        : existing.with(name, itemType, spriteRef, document, now);
        return items.save(item);
    }

    public boolean delete(ProjectId projectId, Slug id) {
        return items.delete(projectId, id);
    }

    /**
     * Validates against the project's schema, and reports the violations at the attribute's own
     * pointers prefixed with {@code /attributes}.
     *
     * <p>Prefixed because the caller sent a whole item, not a bare attributes document: a violation
     * reported at {@code /damage} names a field the request does not have at the top level, and an
     * editor mapping it onto a form would highlight nothing.
     */
    private void validateAttributes(ProjectId projectId, ContentBody attributes) {
        Optional<ContentBody> schema = items.attributeSchema(projectId);
        if (schema.isEmpty()) {
            return;
        }

        List<ContentViolation> violations;
        try {
            violations = schemas.validate(schema.get(), attributes);
        } catch (SchemaValidator.SchemaUnusable unusable) {
            // The project's schema stopped being usable after it was stored -- which should not
            // happen, because it is checked when set. Reported as the project's problem rather than
            // the author's, because it is not the item that is wrong.
            throw new ContentRejected(
                    List.of(
                            ContentViolation.atRoot(
                                    "this project's item schema cannot be used: "
                                            + unusable.getMessage())));
        }

        if (!violations.isEmpty()) {
            throw new ContentRejected(
                    violations.stream()
                            .map(v -> new ContentViolation("/attributes" + v.pointer(), v.message()))
                            .toList());
        }
    }

    public Optional<ContentBody> attributeSchema(ProjectId projectId) {
        return items.attributeSchema(projectId);
    }

    /**
     * Sets the project's item schema, refusing an unusable one now rather than on first use.
     *
     * <p>Existing items are <b>not</b> re-validated. A project tightening its schema would
     * otherwise find that half its catalogue had become unsaveable without anything telling it
     * which half — and a migration is the honest way to handle that, not a failed request.
     */
    public ContentBody replaceAttributeSchema(ProjectId projectId, ContentBody schema) {
        if (schema == null) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/schema", "send a schema, or '{}' for none")));
        }
        try {
            schemas.requireUsable(schema);
        } catch (SchemaValidator.SchemaUnusable unusable) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/schema", unusable.getMessage())));
        }
        return items.replaceAttributeSchema(projectId, schema, clock.instant());
    }

    // ------------------------------------------------------------------ inventory

    public List<InventoryEntry> inventoryOf(ProjectId projectId, PlayerId playerId) {
        return inventory.of(projectId, playerId);
    }

    /**
     * Gives a player several items, all or nothing.
     *
     * <p>The acceptance criterion this exists for. A player who received the sword and not the
     * shield has been given something the game never offered, and the inventory looks perfectly
     * consistent, so nothing appears wrong.
     */
    public List<InventoryEntry> grantAll(
            ProjectId projectId, PlayerId playerId, List<ItemGrant> grants) {

        if (players.find(projectId, playerId).isEmpty()) {
            throw new ContentRejected(
                    List.of(ContentViolation.atRoot("no such player in this project")));
        }
        List<ItemGrant> requested = grants == null ? List.of() : grants;

        return unitOfWork.inOne(
                () -> {
                    Instant now = clock.instant();
                    List<ContentViolation> violations = new ArrayList<>();
                    List<InventoryEntry> after = new ArrayList<>();

                    for (int index = 0; index < requested.size(); index++) {
                        ItemGrant grant = requested.get(index);
                        if (grant.itemId() == null) {
                            violations.add(
                                    new ContentViolation("/items/" + index + "/itemId", "not an item id"));
                            continue;
                        }
                        if (grant.quantity() == 0) {
                            violations.add(
                                    new ContentViolation(
                                            "/items/" + index + "/quantity",
                                            "a grant of zero changes nothing; send a quantity"));
                            continue;
                        }
                        Optional<InventoryEntry> entry =
                                inventory.adjust(projectId, playerId, grant.itemId(), grant.quantity(), now);
                        if (entry.isEmpty()) {
                            // Either the item does not exist in this project, or the player does not
                            // have enough of it to give up. Both are the caller's mistake and both
                            // are reported at the index that caused them.
                            violations.add(
                                    new ContentViolation(
                                            "/items/" + index,
                                            grant.quantity() > 0
                                                    ? "no item '" + grant.itemId() + "' in this project"
                                                    : "the player does not have "
                                                            + Math.abs(grant.quantity())
                                                            + " of '"
                                                            + grant.itemId()
                                                            + "'"));
                            continue;
                        }
                        after.add(entry.get());
                    }

                    if (!violations.isEmpty()) {
                        throw new ContentRejected(violations);
                    }
                    return List.copyOf(after);
                });
    }

    /** One item and how many to add; negative takes them away. */
    public record ItemGrant(Slug itemId, long quantity) {}
}
