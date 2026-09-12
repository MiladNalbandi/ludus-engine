// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import io.ludus.application.content.ApplicationConfig;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.content.ContentBody;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Editing the settings clients read at launch. Editors and above.
 *
 * <p>Taken and returned as a raw {@code String}, like a wave document and for the same reason:
 * binding it to a Java type would mean serialising it back out, which moves the bytes and therefore
 * the ETag that every client validates against.
 */
@RestController
@RequestMapping("/api/v1/admin/app-config")
@Tag(name = "Application configuration")
class AppConfigAdminController {

    private final ApplicationConfig config;
    private final ActiveProject activeProject;

    AppConfigAdminController(ApplicationConfig config, ActiveProject activeProject) {
        this.config = config;
        this.activeProject = activeProject;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "getAppConfig",
            summary = "The current configuration document",
            description = "An empty object when the project has never been configured.")
    ResponseEntity<String> current() {
        return ResponseEntity.ok(config.current(activeProject.id()).body().json());
    }

    @PutMapping(consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(
            operationId = "replaceAppConfig",
            summary = "Replace the configuration document",
            description =
                    "The whole document, not a patch. The engine does not interpret any of these"
                            + " keys, so it has no basis for merging one document into another.")
    ResponseEntity<String> replace(@io.swagger.v3.oas.annotations.parameters.RequestBody(required = true)
                    @RequestBody(required = false)
                    String document) {
        return ResponseEntity.ok(
                config.replace(activeProject.id(), ReceivedDocument.of(document)).body().json());
    }
}
