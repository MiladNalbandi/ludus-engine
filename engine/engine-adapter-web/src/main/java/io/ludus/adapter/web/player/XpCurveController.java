// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.player;

import io.ludus.application.player.PlayerEconomy;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.player.XpStage;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * The project's XP curve, as data the project owns.
 *
 * <p>Its own controller rather than a route under {@code /players}, because it is not about a
 * player: it is a property of the project that every player's stage is derived from. The models
 * this is reshaped from had the curve in code, so a game with a different ramp needed a fork.
 */
@RestController
@RequestMapping("/api/v1/admin/xp-curve")
@Tag(name = "Players")
class XpCurveController {

    private final PlayerEconomy economy;
    private final ActiveProject activeProject;

    XpCurveController(PlayerEconomy economy, ActiveProject activeProject) {
        this.economy = economy;
        this.activeProject = activeProject;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getXpCurve",
            summary = "The project's XP curve",
            description = "Empty when the project has not defined one; a player then has no stage.")
    PlayerDtos.Curve curve() {
        return new PlayerDtos.Curve(
                economy.curve(activeProject.id()).stream().map(PlayerDtos.StageView::of).toList());
    }

    @PutMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "replaceXpCurve",
            summary = "Replace the project's XP curve",
            description =
                    "Wholesale. The stages are only meaningful relative to each other, so editing"
                            + " one in isolation can leave a stage that begins before the one"
                            + " before it. Every problem is reported at once, with the index.")
    PlayerDtos.Curve replaceCurve(
            @io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    PlayerDtos.Curve request) {

        List<XpStage> stages =
                request == null || request.stages() == null
                        ? List.of()
                        : request.stages().stream()
                                .map(view -> new XpStage(view.stage(), view.xpRequired(), view.label()))
                                .toList();

        return new PlayerDtos.Curve(
                economy.replaceCurve(activeProject.id(), stages).stream()
                        .map(PlayerDtos.StageView::of)
                        .toList());
    }
}
