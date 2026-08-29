// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.auth;

import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.identity.RefreshAccessToken;
import io.ludus.application.project.port.in.ActiveProject;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/auth")
@Tag(name = "Authentication")
class AuthController {

    private final AuthenticateUser authenticate;
    private final RefreshAccessToken refresh;
    private final ActiveProject activeProject;

    AuthController(
            AuthenticateUser authenticate,
            RefreshAccessToken refresh,
            ActiveProject activeProject) {
        this.authenticate = authenticate;
        this.refresh = refresh;
        this.activeProject = activeProject;
    }

    @PostMapping("/token")
    @Operation(
            summary = "Exchange an email address and password for tokens",
            description =
                    "Every failure returns the same 401 with the same body. The difference"
                            + " between an unknown address and a wrong password is not something"
                            + " to tell whoever is asking.")
    ResponseEntity<AuthDtos.TokenResponse> token(
            @Valid @RequestBody AuthDtos.TokenRequest request) {
        return ResponseEntity.ok(
                AuthDtos.TokenResponse.of(
                        authenticate.authenticate(
                                activeProject.id(), request.email(), request.password())));
    }

    @PostMapping("/refresh")
    @Operation(
            summary = "Exchange a refresh token for a new pair",
            description =
                    "The presented token is revoked as part of the exchange, so a stolen token"
                            + " and the real one cannot both keep working.")
    ResponseEntity<AuthDtos.TokenResponse> refresh(
            @Valid @RequestBody AuthDtos.RefreshRequest request) {
        return ResponseEntity.ok(
                AuthDtos.TokenResponse.of(
                        refresh.refresh(activeProject.id(), request.refreshToken())));
    }
}
