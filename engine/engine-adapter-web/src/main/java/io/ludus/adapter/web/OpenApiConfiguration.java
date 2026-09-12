// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * The description here ends up in the published OpenAPI document, so it is part of the artifact
 * rather than decoration.
 *
 * <p>The document is committed at {@code docs/api/openapi.json} and {@code OpenApiSnapshotTest}
 * fails the build when it changes, so a change to the public contract is a line in a diff somebody
 * has to approve rather than something that happens quietly.
 *
 * <p>This comment previously said that while none of it was built, which was worse than saying
 * nothing. It is written here again only because it is now true.
 */
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI ludusOpenApi(@Value("${ludus.version:0.0.1-SNAPSHOT}") String version) {
        return new OpenAPI()
                .info(new Info()
                        .title("Ludus Engine API")
                        .version(version)
                        .description("""
                                Backend engine for 2D games. Content is authored in the editor and \
                                served to game clients over the public routes, which are cacheable \
                                and validated by ETag.""")
                        .license(new License()
                                .name("AGPL-3.0-or-later")
                                .url("https://www.gnu.org/licenses/agpl-3.0.txt")));
    }
}
