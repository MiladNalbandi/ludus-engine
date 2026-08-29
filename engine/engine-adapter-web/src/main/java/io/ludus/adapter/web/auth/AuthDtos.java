// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.auth;

import io.ludus.application.identity.IssuedTokens;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import java.time.Instant;

/**
 * The HTTP shapes for authentication. They stay in this module.
 *
 * <p>A DTO that reaches the application layer is a wire format that the application has to keep
 * stable, and then renaming a JSON field means changing a use case. The mapping below is tedious
 * exactly once.
 */
final class AuthDtos {

    private AuthDtos() {}

    record TokenRequest(
            @Schema(example = "you@example.com") @NotBlank String email,
            @Schema(format = "password") @NotBlank String password) {}

    record RefreshRequest(@NotBlank String refreshToken) {}

    @Schema(description = "A pair of tokens. The refresh token is shown once and is not recoverable.")
    record TokenResponse(
            String accessToken,
            String tokenType,
            Instant accessTokenExpiresAt,
            String refreshToken,
            Instant refreshTokenExpiresAt) {

        static TokenResponse of(IssuedTokens tokens) {
            return new TokenResponse(
                    tokens.accessToken(),
                    "Bearer",
                    tokens.accessTokenExpiresAt(),
                    tokens.refreshToken(),
                    tokens.refreshTokenExpiresAt());
        }
    }

    record CurrentCaller(String kind, String subject, String project, String role) {}
}
