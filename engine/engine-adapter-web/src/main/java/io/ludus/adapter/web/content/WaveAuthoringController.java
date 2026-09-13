// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.AuthorWave;
import io.ludus.application.content.BulkAuthoring;
import io.ludus.application.content.WaveCatalogue;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.ContentBody;
import io.ludus.domain.content.Wave;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Schema;
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
    private final BulkAuthoring bulk;
    private final WaveCatalogue catalogue;
    private final ActiveProject activeProject;

    WaveAuthoringController(
            AuthorWave authorWave,
            BulkAuthoring bulk,
            WaveCatalogue catalogue,
            ActiveProject activeProject) {
        this.authorWave = authorWave;
        this.bulk = bulk;
        this.catalogue = catalogue;
        this.activeProject = activeProject;
    }

    /**
     * Imports many documents, all or nothing.
     *
     * <p>The body is a JSON array of documents, taken as a raw string and split by the application
     * layer's reader — not bound to {@code List<Object>}, because binding would parse and
     * re-serialise every document on the way through and move all of their bytes.
     */
    @PostMapping(path = "/bulk", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "importWaves",
            summary = "Create or replace many waves at once",
            description =
                    "All or nothing: one invalid document rejects the whole batch, and every"
                            + " violation is reported with the index of the document that caused"
                            + " it. Imported waves are drafts, like any other save.")
    ResponseEntity<List<WaveDtos.Summary>> importAll(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    String documents) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(
                        bulk.importAll(activeProject.id(), JsonArrays.split(documents)).stream()
                                .map(WaveDtos.Summary::of)
                                .toList());
    }

    @PostMapping(path = "/batch-delete", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "batchDeleteWaves",
            summary = "Delete many waves at once",
            description =
                    "All or nothing. An id that is not there is a violation rather than a silent"
                            + " skip: 'delete these six' is a statement about a known set.")
    ResponseEntity<DeletedResponse> batchDelete(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    BatchDeleteRequest request) {
        List<String> ids = request == null ? null : request.ids();
        return ResponseEntity.ok(new DeletedResponse(bulk.deleteAll(activeProject.id(), ids)));
    }

    @Schema(name = "WaveBatchDeleteRequest")
    record BatchDeleteRequest(List<String> ids) {}

    @Schema(name = "WaveBatchDeleteResult")
    record DeletedResponse(int deleted) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "createWave",
            summary = "Create a wave from a document",
            description =
                    "The document's own id is used. Saving never publishes: a new wave is a draft"
                            + " and invisible to clients until it is published.")
    ResponseEntity<WaveDtos.Summary> create(@io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    String document) {
        Wave saved = authorWave.author(activeProject.id(), Optional.empty(), ReceivedDocument.of(document));
        return ResponseEntity.status(HttpStatus.CREATED).body(WaveDtos.Summary.of(saved));
    }

    @PutMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "replaceWave",
            summary = "Replace a wave's document",
            description = "The id in the URL and the id in the document must agree.")
    WaveDtos.Summary replace(@PathVariable String id, @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    String document) {
        return WaveDtos.Summary.of(
                authorWave.author(
                        activeProject.id(), Optional.of(new Slug(id)), ReceivedDocument.of(document)));
    }

    @GetMapping
    @Operation(operationId = "listWaves", summary = "List every wave, drafts included")
    List<WaveDtos.Summary> list() {
        return catalogue.forAuthors(activeProject.id()).stream().map(WaveDtos.Summary::of).toList();
    }

    @GetMapping("/next-order")
    @Operation(operationId = "nextWaveOrder",
            summary = "An order that would not collide",
            description =
                    "Advisory. The order lives in the document and the author owns it; this only"
                            + " answers what is free right now.")
    int nextOrder() {
        return catalogue.suggestNextOrder(activeProject.id());
    }

    @GetMapping(path = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "getWaveDocument",
            summary = "Fetch a wave's document, draft or not",
            description = "Returns the stored bytes exactly as they were received.")
    ResponseEntity<String> document(@PathVariable String id) {
        return catalogue
                .find(activeProject.id(), new Slug(id))
                .map(wave -> ResponseEntity.ok(wave.body().json()))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/{id}/publish")
    @Operation(operationId = "publishWave", summary = "Publish a wave, making it visible to clients")
    ResponseEntity<WaveDtos.Summary> publish(@PathVariable String id) {
        return setPublished(id, true);
    }

    @PostMapping("/{id}/unpublish")
    @Operation(operationId = "unpublishWave", summary = "Withdraw a wave. Clients stop seeing it entirely, as a 404.")
    ResponseEntity<WaveDtos.Summary> unpublish(@PathVariable String id) {
        return setPublished(id, false);
    }

    @DeleteMapping("/{id}")
    @Operation(operationId = "deleteWave", summary = "Delete a wave")
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
