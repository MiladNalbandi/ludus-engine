// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.WaveCatalogue;
import io.ludus.application.content.WaveLevels;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.WaveLevel;
import io.ludus.domain.content.WaveLevelId;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;
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
 * Assembling waves into levels, and choosing which one is being played. Editors and above.
 *
 * <p>Every response marks each member wave as published or not, because the public route serves
 * only the published ones and the difference is otherwise invisible until a player reports it.
 */
@RestController
@RequestMapping("/api/v1/admin/wave-levels")
@Tag(name = "Wave levels")
class WaveLevelAdminController {

    private final WaveLevels levels;
    private final WaveCatalogue catalogue;
    private final ActiveProject activeProject;

    WaveLevelAdminController(
            WaveLevels levels, WaveCatalogue catalogue, ActiveProject activeProject) {
        this.levels = levels;
        this.catalogue = catalogue;
        this.activeProject = activeProject;
    }

    @GetMapping
    @Operation(operationId = "listWaveLevels", summary = "Every level in the project")
    List<WaveLevelDtos.Summary> list() {
        ProjectId project = activeProject.id();
        Set<String> published = publishedIds(project);
        Optional<WaveLevelId> active = levels.active(project).map(WaveLevel::id);
        return levels.list(project).stream()
                .map(level -> WaveLevelDtos.Summary.of(level, active.filter(level.id()::equals).isPresent(), published))
                .toList();
    }

    @GetMapping("/{id}")
    @Operation(operationId = "getWaveLevel", summary = "One level")
    ResponseEntity<WaveLevelDtos.Summary> find(@PathVariable String id) {
        ProjectId project = activeProject.id();
        return parse(id)
                .flatMap(levelId -> levels.find(project, levelId))
                .map(level -> ResponseEntity.ok(summarise(project, level)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "createWaveLevel",
            summary = "Create a level",
            description =
                    "The waves are listed in play order. Creating a level never activates it;"
                            + " activation is a separate call.")
    ResponseEntity<WaveLevelDtos.Summary> create(@RequestBody WaveLevelDtos.Request request) {
        ProjectId project = activeProject.id();
        WaveLevel created =
                levels.create(project, request.name(), request.description(), slugs(request));
        return ResponseEntity.status(HttpStatus.CREATED).body(summarise(project, created));
    }

    @PutMapping(path = "/{id}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "updateWaveLevel",
            summary = "Rename or resequence a level",
            description = "The wave list is replaced wholesale, in the order given.")
    ResponseEntity<WaveLevelDtos.Summary> update(
            @PathVariable String id, @RequestBody WaveLevelDtos.Request request) {
        ProjectId project = activeProject.id();
        return parse(id)
                .flatMap(
                        levelId ->
                                levels.update(
                                        project,
                                        levelId,
                                        request.name(),
                                        request.description(),
                                        slugs(request)))
                .map(level -> ResponseEntity.ok(summarise(project, level)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping("/{id}/activate")
    @Operation(operationId = "activateWaveLevel",
            summary = "Make this the level players receive",
            description =
                    "Replaces whatever was active. A project has at most one active level, which"
                            + " the database guarantees rather than this endpoint.")
    ResponseEntity<WaveLevelDtos.Summary> activate(@PathVariable String id) {
        ProjectId project = activeProject.id();
        return parse(id)
                .filter(levelId -> levels.activate(project, levelId))
                .flatMap(levelId -> levels.find(project, levelId))
                .map(level -> ResponseEntity.ok(summarise(project, level)))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @DeleteMapping("/{id}")
    @Operation(operationId = "deleteWaveLevel",
            summary = "Delete a level",
            description =
                    "The waves themselves are untouched; only their membership of this level goes."
                            + " Deleting the active level leaves the project with none active.")
    ResponseEntity<Void> delete(@PathVariable String id) {
        ProjectId project = activeProject.id();
        boolean removed = parse(id).map(levelId -> levels.delete(project, levelId)).orElse(false);
        return removed ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
    }

    /**
     * A malformed id is the same answer as one that is not there.
     *
     * <p>Telling them apart would say which ids are shaped correctly, and there is nothing a caller
     * could usefully do with either answer that they could not do with one.
     */
    private Optional<WaveLevelId> parse(String id) {
        try {
            return Optional.of(WaveLevelId.of(id));
        } catch (IllegalArgumentException notAnId) {
            return Optional.empty();
        }
    }

    private List<Slug> slugs(WaveLevelDtos.Request request) {
        // A malformed slug is not a 500. It cannot name a wave that exists, so it is reported by
        // the use case as a missing wave at the index that carried it, alongside any others.
        return request.waves() == null
                ? List.of()
                : request.waves().stream().map(WaveLevelAdminController::slugOrPlaceholder).toList();
    }

    private static Slug slugOrPlaceholder(String candidate) {
        return Slug.isValid(candidate) ? new Slug(candidate) : null;
    }

    private WaveLevelDtos.Summary summarise(ProjectId project, WaveLevel level) {
        boolean active = levels.active(project).map(WaveLevel::id).filter(level.id()::equals).isPresent();
        return WaveLevelDtos.Summary.of(level, active, publishedIds(project));
    }

    private Set<String> publishedIds(ProjectId project) {
        return catalogue.published(project).stream()
                .map(wave -> wave.id().value())
                .collect(Collectors.toSet());
    }
}
