// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.AuthorWave;
import io.ludus.application.content.WaveCatalogue;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Optional;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Authoring waves. Editors and above; never a game client.
 *
 * <p>Bodies are taken as a raw {@code String} rather than a mapped object, and that is the point.
 * Binding the document to a Java type would mean serialising it back out to store it, which moves
 * the bytes and therefore every ETag. The controller's job here is to hand the received characters
 * to the application untouched.
 */
@RestController
@RequestMapping("/api/v1/admin/waves")
@Tag(name = "Wave authoring")
class WaveAuthoringController {

    private final AuthorWave authorWave;
    private final WaveCatalogue catalogue;
    private final ActiveProject activeProject;

    WaveAuthoringController(
            AuthorWave authorWave, WaveCatalogue catalogue, ActiveProject activeProject) {
        this.authorWave = authorWave;
        this.catalogue = catalogue;
        this.activeProject = activeProject;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "Create a wave from a document",
            description =
                    "The document's own id is used. Saving never publishes: a new wave is a draft"
                            + " and invisible to clients until it is published.")
    ResponseEntity<WaveDtos.Summary> create(@RequestBody String document) {
        Wave saved = authorWave.author(activeProject.id(), Optional.empty(), new ContentBody(document));
        return ResponseEntity.status(HttpStatus.CREATED).body(WaveDtos.Summary.of(saved));
    }

    @PutMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "Replace a wave's document",
            description = "The id in the URL and the id in the document must agree.")
    WaveDtos.Summary replace(@PathVariable String id, @RequestBody String document) {
        return WaveDtos.Summary.of(
                authorWave.author(
                        activeProject.id(), Optional.of(new Slug(id)), new ContentBody(document)));
    }

    @GetMapping
    @Operation(summary = "List every wave, drafts included")
    List<WaveDtos.Summary> list() {
        return catalogue.forAuthors(activeProject.id()).stream().map(WaveDtos.Summary::of).toList();
    }

    @GetMapping("/next-order")
    @Operation(
            summary = "An order that would not collide",
            description =
                    "Advisory. The order lives in the document and the author owns it; this only"
                            + " answers what is free right now.")
    int nextOrder() {
        return catalogue.suggestNextOrder(activeProject.id());
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            summary = "Fetch a wave's document, draft or not",
            description = "Returns the stored bytes exactly as they were received.")
    ResponseEntity<String> document(@PathVariable String id) {
        return catalogue
                .find(activeProject.id(), new Slug(id))
                .map(wave -> ResponseEntity.ok(wave.body().json()))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/{id}/publish")
    @Operation(summary = "Publish a wave, making it visible to clients")
    ResponseEntity<WaveDtos.Summary> publish(@PathVariable String id) {
        return setPublished(id, true);
    }

    @PostMapping("/{id}/unpublish")
    @Operation(summary = "Withdraw a wave. Clients stop seeing it entirely, as a 404.")
    ResponseEntity<WaveDtos.Summary> unpublish(@PathVariable String id) {
        return setPublished(id, false);
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "Delete a wave")
    ResponseEntity<Void> delete(@PathVariable String id) {
        return catalogue.delete(activeProject.id(), new Slug(id))
                ? ResponseEntity.noContent().build()
                : ResponseEntity.notFound().build();
    }

    private ResponseEntity<WaveDtos.Summary> setPublished(String id, boolean published) {
        return catalogue
                .setPublished(activeProject.id(), new Slug(id), published)
                .map(WaveDtos.Summary::of)
                .map(ResponseEntity::ok)
                // 404 rather than 403 for another project's wave: from outside, "not yours" and
                // "not there" must be indistinguishable.
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
