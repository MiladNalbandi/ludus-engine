// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.auth;

import io.ludus.application.identity.Caller;
import io.ludus.application.identity.port.in.CurrentCaller;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Reports who the engine thinks you are.
 *
 * <p>Small, and worth having: it answers "is my token actually working" without needing anything
 * else to exist yet, and it is what an integration test uses to prove that a role and a project
 * survived the whole filter chain.
 */
@RestController
@RequestMapping("/api/v1/me")
@Tag(name = "Authentication")
class CurrentCallerController {

    private final CurrentCaller currentCaller;

    CurrentCallerController(CurrentCaller currentCaller) {
        this.currentCaller = currentCaller;
    }

    @GetMapping
    @Operation(summary = "The identity behind the credential you presented")
    AuthDtos.CurrentCaller me() {
        Caller caller = currentCaller.require();
        return new AuthDtos.CurrentCaller(
                caller.kind().name(),
                caller.subject(),
                caller.projectId().toString(),
                caller.role().name());
    }
}
