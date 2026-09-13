// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

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
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;

/**
 * Items, their project-owned schema, and inventory grants.
 *
 * <p>The two that matter: a violation inside the attributes is reported at a pointer an editor can
 * map onto a form, and a grant of several items is all or nothing. The second is easy to claim and
 * easy to get wrong, and when it is wrong the inventory looks perfectly consistent.
 */
class ItemCatalogueTest {

    private static final Instant NOW = Instant.parse("2026-09-12T15:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final Slug SWORD = new Slug("sword");
    private static final Slug SHIELD = new Slug("shield");

    private final Items items = new Items();
    private final Inventory inventory = new Inventory();
    private final Players players = new Players();
    private final Validator schemas = new Validator();
    private final RollingBack unitOfWork = new RollingBack();
    private final ItemCatalogue catalogue =
            new ItemCatalogue(
                    items, inventory, players, schemas, unitOfWork, Clock.fixed(NOW, ZoneOffset.UTC));

    private PlayerId aPlayer() {
        Player player = Player.firstSeen(PlayerId.random(), MINE, "device-one", NOW);
        players.save(player);
        return player.id();
    }

    private Item anItem(Slug id) {
        return catalogue.save(MINE, id, id.value(), "weapon", null, new ContentBody("{\"damage\":5}"));
    }

    // ------------------------------------------------------------------ items

    @Test
    void an_item_is_created_with_its_attributes_untouched() {
        Item saved =
                catalogue.save(
                        MINE, SWORD, "Sword", "weapon", "sprites/sword.png",
                        new ContentBody("{\"damage\":5,   \"reach\":1.0}"));

        assertThat(saved.attributes().json())
                .as("the project owns this document; the engine stores what it was sent")
                .isEqualTo("{\"damage\":5,   \"reach\":1.0}");
        assertThat(saved.spriteRef()).isEqualTo("sprites/sword.png");
    }

    @Test
    void an_item_with_no_attributes_gets_an_empty_document_rather_than_null() {
        assertThat(catalogue.save(MINE, SWORD, "Sword", "weapon", null, null).attributes().json())
                .isEqualTo("{}");
    }

    @Test
    void an_item_type_outside_the_projects_vocabulary_format_is_refused() {
        assertThatThrownBy(
                        () -> catalogue.save(MINE, SWORD, "Sword", "Weapon!", null, null))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/itemType"));
    }

    @Test
    void an_item_with_no_name_is_refused() {
        assertThatThrownBy(() -> catalogue.save(MINE, SWORD, "  ", "weapon", null, null))
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void saving_an_item_twice_replaces_it_and_keeps_its_creation_time() {
        Item first = anItem(SWORD);
        Item second =
                catalogue.save(MINE, SWORD, "Better sword", "weapon", null, new ContentBody("{\"damage\":9}"));

        assertThat(second.createdAt()).isEqualTo(first.createdAt());
        assertThat(second.name()).isEqualTo("Better sword");
        assertThat(catalogue.list(MINE)).hasSize(1);
    }

    // ------------------------------------------------------------------ the project's schema

    @Test
    void attribute_violations_are_reported_under_the_attributes_pointer() {
        schemas.violations = List.of(new ContentViolation("/damage", "must be an integer"));
        catalogue.replaceAttributeSchema(MINE, new ContentBody("{\"type\":\"object\"}"));

        assertThatThrownBy(
                        () ->
                                catalogue.save(
                                        MINE, SWORD, "Sword", "weapon", null,
                                        new ContentBody("{\"damage\":\"lots\"}")))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .as("the caller sent a whole item, not a bare attributes document")
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/attributes/damage"));
    }

    @Test
    void a_project_with_no_schema_validates_nothing() {
        // A game that has not decided what its items look like should not be stopped from making
        // one. The validator is not even consulted.
        catalogue.save(MINE, SWORD, "Sword", "weapon", null, new ContentBody("{\"anything\":true}"));

        assertThat(schemas.calls).isZero();
    }

    @Test
    void an_unusable_schema_is_refused_when_it_is_set() {
        schemas.unusable = "an item schema may only use local $ref targets";

        assertThatThrownBy(
                        () ->
                                catalogue.replaceAttributeSchema(
                                        MINE, new ContentBody("{\"$ref\":\"https://attacker.example/s.json\"}")))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .singleElement()
                                        .extracting(ContentViolation::pointer)
                                        .isEqualTo("/schema"));
        assertThat(items.schema).as("and is not stored").isNull();
    }

    @Test
    void setting_a_schema_does_not_re_validate_existing_items() {
        anItem(SWORD);
        schemas.violations = List.of(new ContentViolation("/damage", "must be at least 10"));

        // Tightening a schema would otherwise make half a catalogue unsaveable with nothing saying
        // which half. A migration is the honest way to handle that, not a failed request.
        catalogue.replaceAttributeSchema(MINE, new ContentBody("{\"type\":\"object\"}"));

        assertThat(catalogue.find(MINE, SWORD)).isPresent();
    }

    // ------------------------------------------------------------------ inventory

    @Test
    void a_grant_of_several_items_applies_all_of_them() {
        PlayerId player = aPlayer();
        anItem(SWORD);
        anItem(SHIELD);

        List<InventoryEntry> after =
                catalogue.grantAll(
                        MINE,
                        player,
                        List.of(
                                new ItemCatalogue.ItemGrant(SWORD, 1),
                                new ItemCatalogue.ItemGrant(SHIELD, 2)));

        assertThat(after)
                .extracting(e -> e.itemId().value(), InventoryEntry::quantity)
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("sword", 1L),
                        org.assertj.core.groups.Tuple.tuple("shield", 2L));
    }

    @Test
    void one_unknown_item_rolls_the_whole_grant_back() {
        PlayerId player = aPlayer();
        anItem(SWORD);

        assertThatThrownBy(
                        () ->
                                catalogue.grantAll(
                                        MINE,
                                        player,
                                        List.of(
                                                new ItemCatalogue.ItemGrant(SWORD, 1),
                                                new ItemCatalogue.ItemGrant(new Slug("ghost"), 1))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .extracting(ContentViolation::pointer)
                                        .containsExactly("/items/1"));

        assertThat(unitOfWork.rolledBack)
                .as("a player who got the sword and not the shield was given something the game never offered")
                .isTrue();
    }

    @Test
    void taking_more_than_the_player_has_is_refused() {
        PlayerId player = aPlayer();
        anItem(SWORD);
        catalogue.grantAll(MINE, player, List.of(new ItemCatalogue.ItemGrant(SWORD, 1)));

        assertThatThrownBy(
                        () ->
                                catalogue.grantAll(
                                        MINE, player, List.of(new ItemCatalogue.ItemGrant(SWORD, -3))))
                .isInstanceOf(ContentRejected.class)
                .satisfies(
                        thrown ->
                                assertThat(((ContentRejected) thrown).violations())
                                        .singleElement()
                                        .extracting(ContentViolation::message)
                                        .asString()
                                        .contains("does not have 3"));
    }

    @Test
    void a_grant_of_zero_is_refused_rather_than_silently_doing_nothing() {
        PlayerId player = aPlayer();
        anItem(SWORD);

        assertThatThrownBy(
                        () ->
                                catalogue.grantAll(
                                        MINE, player, List.of(new ItemCatalogue.ItemGrant(SWORD, 0))))
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void granting_to_a_player_that_is_not_there_is_refused_before_any_write() {
        anItem(SWORD);

        assertThatThrownBy(
                        () ->
                                catalogue.grantAll(
                                        MINE,
                                        PlayerId.random(),
                                        List.of(new ItemCatalogue.ItemGrant(SWORD, 1))))
                .isInstanceOf(ContentRejected.class);
        assertThat(inventory.adjustments).isEmpty();
    }

    @Test
    void deleting_an_item_is_reported() {
        anItem(SWORD);

        assertThat(catalogue.delete(MINE, SWORD)).isTrue();
        assertThat(catalogue.delete(MINE, SWORD)).isFalse();
    }

    // ------------------------------------------------------------------ fakes

    private static final class RollingBack implements UnitOfWork {
        private boolean rolledBack;

        @Override
        public <T> T inOne(Supplier<T> work) {
            try {
                return work.get();
            } catch (RuntimeException thrown) {
                rolledBack = true;
                throw thrown;
            }
        }
    }

    private static final class Validator implements SchemaValidator {
        private List<ContentViolation> violations = List.of();
        private String unusable;
        private int calls;

        @Override
        public List<ContentViolation> validate(ContentBody schema, ContentBody document) {
            calls++;
            return violations;
        }

        @Override
        public void requireUsable(ContentBody schema) {
            if (unusable != null) {
                throw new SchemaUnusable(unusable);
            }
        }
    }

    private static final class Items implements ItemRepository {
        private final Map<Slug, Item> byId = new LinkedHashMap<>();
        private ContentBody schema;

        @Override
        public Item save(Item item) {
            byId.put(item.id(), item);
            return item;
        }

        @Override
        public Optional<Item> find(ProjectId projectId, Slug id) {
            return Optional.ofNullable(byId.get(id)).filter(i -> i.projectId().equals(projectId));
        }

        @Override
        public List<Item> list(ProjectId projectId) {
            return byId.values().stream().filter(i -> i.projectId().equals(projectId)).toList();
        }

        @Override
        public boolean delete(ProjectId projectId, Slug id) {
            return find(projectId, id).isPresent() && byId.remove(id) != null;
        }

        @Override
        public Optional<ContentBody> attributeSchema(ProjectId projectId) {
            return Optional.ofNullable(schema);
        }

        @Override
        public ContentBody replaceAttributeSchema(ProjectId projectId, ContentBody body, Instant at) {
            schema = body;
            return body;
        }
    }

    private final class Inventory implements InventoryRepository {
        private final Map<String, InventoryEntry> held = new LinkedHashMap<>();
        private final List<String> adjustments = new ArrayList<>();

        @Override
        public List<InventoryEntry> of(ProjectId projectId, PlayerId playerId) {
            return held.entrySet().stream()
                    .filter(e -> e.getKey().startsWith(playerId + "/"))
                    .map(Map.Entry::getValue)
                    .toList();
        }

        @Override
        public Optional<InventoryEntry> adjust(
                ProjectId projectId, PlayerId playerId, Slug itemId, long delta, Instant at) {
            adjustments.add(playerId + "/" + itemId + ":" + delta);

            // The real one is refused by the composite foreign key when the item does not exist.
            // The fake must refuse too, or a test would pass here and fail against a real schema.
            if (items.find(projectId, itemId).isEmpty()) {
                return Optional.empty();
            }
            String key = playerId + "/" + itemId;
            InventoryEntry existing = held.get(key);
            long next = (existing == null ? 0 : existing.quantity()) + delta;
            if (next < 0) {
                return Optional.empty();
            }
            InventoryEntry updated = new InventoryEntry(itemId, next, at);
            held.put(key, updated);
            return Optional.of(updated);
        }
    }

    private static final class Players implements PlayerRepository {
        private final Map<PlayerId, Player> saved = new LinkedHashMap<>();

        @Override
        public Player save(Player player) {
            saved.put(player.id(), player);
            return player;
        }

        @Override
        public Optional<Player> find(ProjectId projectId, PlayerId id) {
            return Optional.ofNullable(saved.get(id)).filter(p -> p.projectId().equals(projectId));
        }

        @Override
        public Optional<Player> findByExternalId(ProjectId projectId, String externalId) {
            return saved.values().stream()
                    .filter(p -> p.projectId().equals(projectId) && p.externalId().equals(externalId))
                    .findFirst();
        }

        @Override
        public List<Player> page(ProjectId projectId, PlayerPageCursor after, int limit) {
            return saved.values().stream().filter(p -> p.projectId().equals(projectId)).limit(limit).toList();
        }

        @Override
        public long count(ProjectId projectId) {
            return saved.values().stream().filter(p -> p.projectId().equals(projectId)).count();
        }

        @Override
        public boolean delete(ProjectId projectId, PlayerId id) {
            return find(projectId, id).isPresent() && saved.remove(id) != null;
        }
    }
}
