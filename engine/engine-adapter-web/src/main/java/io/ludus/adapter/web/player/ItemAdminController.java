// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.ItemCatalogue;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Defining items, and the schema their attributes are checked against. Editors and above. */
@RestController
@RequestMapping("/api/v1/admin/items")
@Tag(name = "Items")
class ItemAdminController {

    private final ItemCatalogue catalogue;
    private final ActiveProject activeProject;

    ItemAdminController(ItemCatalogue catalogue, ActiveProject activeProject) {
        this.catalogue = catalogue;
        this.activeProject = activeProject;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "listItems", summary = "Every item this project defines")
    List<ItemDtos.View> list() {
        return catalogue.list(activeProject.id()).stream().map(ItemDtos.View::of).toList();
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "getItem", summary = "One item")
    ResponseEntity<ItemDtos.View> find(@PathVariable String id) {
        return slug(id)
                .flatMap(itemId -> catalogue.find(activeProject.id(), itemId))
                .map(item -> ResponseEntity.ok(ItemDtos.View.of(item)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PutMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "saveItem",
            summary = "Create or replace an item",
            description =
                    "Attributes are validated against this project's own item schema, if it has"
                            + " declared one. Violations are reported at /attributes plus the"
                            + " pointer inside the document.")
    ItemDtos.View save(
            @PathVariable String id,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    ItemDtos.Request request) {

        Slug itemId =
                slug(id).orElseThrow(
                        () ->
                                new ContentRejected(
                                        List.of(
                                                new ContentViolation(
                                                        "/id",
                                                        "'" + id + "' is not an item id; expected ^[a-z0-9_]+$"))));

        return ItemDtos.View.of(
                catalogue.save(
                        activeProject.id(),
                        itemId,
                        request == null ? null : request.name(),
                        request == null ? null : request.itemType(),
                        request == null ? null : request.spriteRef(),
                        request == null || request.attributes() == null || request.attributes().isBlank()
                                ? null
                                : new ContentBody(request.attributes())));
    }

    @DeleteMapping("/{id}")
    @Operation(
            operationId = "deleteItem",
            summary = "Delete an item",
            description = "It is removed from every player's inventory too, by foreign key.")
    ResponseEntity<Void> delete(@PathVariable String id) {
        boolean removed = slug(id).map(itemId -> catalogue.delete(activeProject.id(), itemId)).orElse(false);
        return removed ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
    }

    private java.util.Optional<Slug> slug(String candidate) {
        return Slug.isValid(candidate) ? java.util.Optional.of(new Slug(candidate)) : java.util.Optional.empty();
    }
}
