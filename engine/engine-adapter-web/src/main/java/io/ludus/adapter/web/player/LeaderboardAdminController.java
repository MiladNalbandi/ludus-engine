// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.content.ContentRejected;
import io.ludus.application.content.ContentViolation;
import io.ludus.application.player.Leaderboards;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.shared.Slug;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import java.util.Optional;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** Defining boards, and reading them as an administrator. Editors and above. */
@RestController
@RequestMapping("/api/v1/admin/leaderboards")
@Tag(name = "Leaderboards")
class LeaderboardAdminController {

    private final Leaderboards leaderboards;
    private final ActiveProject activeProject;

    LeaderboardAdminController(Leaderboards leaderboards, ActiveProject activeProject) {
        this.leaderboards = leaderboards;
        this.activeProject = activeProject;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "listLeaderboardsAsAdmin", summary = "Every board")
    List<LeaderboardDtos.BoardView> list() {
        return leaderboards.list(activeProject.id()).stream()
                .map(LeaderboardDtos.BoardView::of)
                .toList();
    }

    @GetMapping(path = "/{boardId}", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(operationId = "getLeaderboardPageAsAdmin", summary = "A page of a board")
    ResponseEntity<LeaderboardDtos.PageView> page(
            @PathVariable String boardId,
            @RequestParam(required = false) Integer limit) {

        return board(boardId)
                .map(
                        id ->
                                ResponseEntity.ok(
                                        LeaderboardDtos.PageView.of(
                                                leaderboards.page(
                                                        activeProject.id(), id, null,
                                                        limit == null ? 20 : limit))))
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PutMapping(path = "/{boardId}", consumes = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "saveLeaderboard",
            summary = "Create or replace a board",
            description =
                    "`descending` says whether a bigger number is better. It belongs to the board"
                            + " rather than to a query, so two callers cannot disagree about a"
                            + " player's rank.")
    LeaderboardDtos.BoardView save(
            @PathVariable String boardId,
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    LeaderboardDtos.BoardRequest request) {

        Slug id =
                board(boardId)
                        .orElseThrow(
                                () ->
                                        new ContentRejected(
                                                List.of(
                                                        new ContentViolation(
                                                                "/boardId",
                                                                "'" + boardId + "' is not a board id;"
                                                                        + " expected ^[a-z0-9_]+$"))));

        return LeaderboardDtos.BoardView.of(
                leaderboards.save(
                        activeProject.id(),
                        id,
                        request == null ? null : request.name(),
                        request == null || request.descending() == null || request.descending()));
    }

    @DeleteMapping("/{boardId}")
    @Operation(
            operationId = "deleteLeaderboard",
            summary = "Delete a board",
            description = "Its scores go with it, by foreign key.")
    ResponseEntity<Void> delete(@PathVariable String boardId) {
        boolean removed = board(boardId).map(id -> leaderboards.delete(activeProject.id(), id)).orElse(false);
        return removed ? ResponseEntity.noContent().build() : ResponseEntity.notFound().build();
    }

    private Optional<Slug> board(String candidate) {
        return Slug.isValid(candidate) ? Optional.of(new Slug(candidate)) : Optional.empty();
    }
}
