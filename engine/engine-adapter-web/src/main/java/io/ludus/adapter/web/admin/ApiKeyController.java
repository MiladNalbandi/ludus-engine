// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.admin;

import io.ludus.application.identity.ApiKeys;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.identity.ApiKeyId;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Issuing and revoking API keys. Administrators only, enforced by the filter chain.
 *
 * <p>Under {@code /api/v1/admin}, which is a prefix the chain matches on rather than a convention.
 * A new endpoint added here is an administrator endpoint because of where it is, not because
 * somebody remembered to annotate it.
 */
@RestController
@RequestMapping("/api/v1/admin/api-keys")
@Tag(name = "API keys")
class ApiKeyController {

    private final ApiKeys apiKeys;
    private final ActiveProject activeProject;

    ApiKeyController(ApiKeys apiKeys, ActiveProject activeProject) {
        this.apiKeys = apiKeys;
        this.activeProject = activeProject;
    }

    @PostMapping
    @Operation(summary = "Mint a key. The response is the only time it is shown.")
    ResponseEntity<ApiKeyDtos.CreatedResponse> create(
            @Valid @RequestBody ApiKeyDtos.CreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(
                        ApiKeyDtos.CreatedResponse.of(
                                apiKeys.issue(activeProject.id(), request.name())));
    }

    @GetMapping
    @Operation(summary = "List keys, including revoked ones")
    List<ApiKeyDtos.Summary> list() {
        return apiKeys.list(activeProject.id()).stream().map(ApiKeyDtos.Summary::of).toList();
    }

    @DeleteMapping("/{id}")
    @Operation(
            summary = "Revoke a key",
            description =
                    "The row is kept and stamped, not deleted: when a key stopped working is a"
                            + " question people ask after an incident.")
    ResponseEntity<ApiKeyDtos.Summary> revoke(@PathVariable UUID id) {
        return apiKeys.revoke(activeProject.id(), new ApiKeyId(id))
                .map(ApiKeyDtos.Summary::of)
                .map(ResponseEntity::ok)
                // 404, not 403. Telling a caller that a key exists but belongs to another project
                // is the leak; from outside, "not yours" and "not there" must look identical.
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
