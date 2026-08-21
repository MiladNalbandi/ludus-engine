// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.smoke;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

/**
 * Proves the composition root actually composes: every module on the classpath, every
 * auto-configuration satisfied, and the operational endpoints reachable. Cheap, and it catches
 * the class of breakage that only shows up when the jar is started for real.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class ApplicationContextTest {

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;

    ApplicationContextTest(@Autowired TestRestTemplate rest) {
        this.rest = rest;
    }

    @Test
    void health_endpoint_reports_up() {
        ResponseEntity<String> response =
                rest.getForEntity("http://localhost:" + port + "/actuator/health", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("\"status\":\"UP\"");
    }

    @Test
    void openapi_document_is_served_and_names_the_engine() {
        ResponseEntity<String> response =
                rest.getForEntity("http://localhost:" + port + "/api-docs", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("Ludus Engine API");
    }

    @Test
    void prometheus_endpoint_is_exposed_so_operators_can_bring_their_own_stack() {
        ResponseEntity<String> response =
                rest.getForEntity("http://localhost:" + port + "/actuator/prometheus", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
    }

    @Test
    void everything_that_is_not_deliberately_open_is_denied() {
        ResponseEntity<String> response =
                rest.getForEntity("http://localhost:" + port + "/api/v1/anything", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
    }
}
