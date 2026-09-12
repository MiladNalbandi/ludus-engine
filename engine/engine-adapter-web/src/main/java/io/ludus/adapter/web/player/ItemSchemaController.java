// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.ItemCatalogue;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.ContentBody;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The schema a project's item attributes are validated against.
 *
 * <p>Its own path rather than {@code /items/schema}, which would have shadowed an item legitimately
 * called {@code schema}: Spring prefers a literal segment over a path variable, so that item would
 * simply have been unreachable — and nothing would have said so. The same reason the XP curve is
 * not {@code /players/xp-curve}.
 */
@RestController
@RequestMapping("/api/v1/admin/item-schema")
@Tag(name = "Items")
class ItemSchemaController {

    private final ItemCatalogue catalogue;
    private final ActiveProject activeProject;

    ItemSchemaController(ItemCatalogue catalogue, ActiveProject activeProject) {
        this.catalogue = catalogue;
        this.activeProject = activeProject;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getItemSchema",
            summary = "The project's item-attribute schema",
            description = "An empty object when the project has not declared one, which validates nothing.")
    ResponseEntity<String> schema() {
        return ResponseEntity.ok(
                catalogue.attributeSchema(activeProject.id()).map(ContentBody::json).orElse("{}"));
    }

    @PutMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "replaceItemSchema",
            summary = "Replace the project's item-attribute schema",
            description =
                    "Refused now rather than on first use if it is unusable. Remote $ref targets"
                            + " are rejected: the engine will not fetch a URL chosen by whoever"
                            + " wrote the schema. Existing items are not re-validated.")
    ResponseEntity<String> replaceSchema(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    String schema) {

        if (schema == null || schema.isBlank()) {
            throw new ContentRejected(
                    List.of(new ContentViolation("/schema", "send a schema, or '{}' for none")));
        }
        return ResponseEntity.ok(
                catalogue.replaceAttributeSchema(activeProject.id(), new ContentBody(schema)).json());
    }

}
