// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.admin;

import io.ludus.application.identity.ApiKeys;
import io.ludus.domain.identity.ApiKey;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;

final class ApiKeyDtos {

    private ApiKeyDtos() {}

    record CreateRequest(
            @NotBlank @Size(max = ApiKey.MAX_NAME_LENGTH)
                    @Schema(example = "android-client", description = "So a human can tell keys apart")
                    String name) {}

    @Schema(
            description =
                    "The only response that ever contains the key itself. It is stored as a"
                            + " digest, so it cannot be shown again by anyone, including whoever"
                            + " runs the database.")
    record CreatedResponse(
            String id, String name, String prefix, String role, Instant createdAt, String key) {

        static CreatedResponse of(ApiKeys.NewApiKey issued) {
            ApiKey key = issued.key();
            return new CreatedResponse(
                    key.id().toString(),
                    key.name(),
                    key.prefix(),
                    key.role().name(),
                    key.createdAt(),
                    issued.plaintext());
        }
    }

    /** Everything about a key except the key. */
    record Summary(
            String id,
            String name,
            String prefix,
            String role,
            Instant createdAt,
            Instant revokedAt) {

        static Summary of(ApiKey key) {
            return new Summary(
                    key.id().toString(),
                    key.name(),
                    key.prefix(),
                    key.role().name(),
                    key.createdAt(),
                    key.revokedAt());
        }
    }
}
