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
 * <p>This comment used to claim the document was committed under {@code docs/api} and diffed in CI.
 * It is not, and never was — there is no snapshot, no plugin and no diff step. That is an
 * acceptance criterion of <a href="https://github.com/MiladNalbandi/ludus-engine/issues/8">#8</a>
 * and is genuinely unbuilt, so the claim is removed rather than left to be believed. A comment
 * asserting a guarantee that does not exist is the same problem as a green check that means
 * nothing, and this project has had enough of those.
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
