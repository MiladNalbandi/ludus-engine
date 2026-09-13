// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.domain.player.InventoryEntry;
import io.ludus.domain.player.Item;
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.List;

final class ItemDtos {

    private ItemDtos() {}

    /**
     * An item, with its attributes as a raw JSON string.
     *
     * <p>A {@code String}, not a mapped object. Binding the attributes to a type would mean
     * serialising them back out to store them, which moves the bytes — and the attributes are a
     * document the project owns, exactly like a wave. The controller hands the received characters
     * to the application untouched.
     */
    @Schema(name = "ItemView", description = "An item the project defines. Attributes are the project's own shape.")
    record View(
            String id,
            String name,
            String itemType,
            String spriteRef,
            String attributes,
            Instant createdAt,
            Instant updatedAt) {

        static View of(Item item) {
            return new View(
                    item.id().value(),
                    item.name(),
                    item.itemType(),
                    item.spriteRef(),
                    item.attributes().json(),
                    item.createdAt(),
                    item.updatedAt());
        }
    }

    @Schema(name = "ItemRequest", description = "An item to create or replace.")
    record Request(String name, String itemType, String spriteRef, String attributes) {}

    @Schema(name = "InventoryEntryView", description = "How many of one item a player holds.")
    record EntryView(String itemId, long quantity, Instant updatedAt) {

        static EntryView of(InventoryEntry entry) {
            return new EntryView(entry.itemId().value(), entry.quantity(), entry.updatedAt());
        }
    }

    @Schema(name = "PlayerInventory", description = "Everything a player holds.")
    record Inventory(List<EntryView> items) {}

    @Schema(name = "ItemGrantRequest", description = "An item and how many; negative takes them away.")
    record GrantRequest(String itemId, Long quantity) {}

    @Schema(name = "InventoryGrantRequest", description = "Several items to grant together, or not at all.")
    record GrantsRequest(List<GrantRequest> items) {}
}
