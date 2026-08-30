// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.content;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.identity.IssuedTokens;
import io.ludus.application.project.port.in.ActiveProject;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

/**
 * The whole authoring path, over HTTP, with a real document.
 *
 * <p>Uses the demo waves in {@code samples/waves} rather than a fixture written for the test. They
 * are the same files the schema conformance test validates and the same ones a reader is pointed at
 * from the documentation, so if the engine cannot store them the documentation is wrong.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class WaveAuthoringIntegrationTest {

    private static final Path SAMPLES = Path.of("..", "..", "samples", "waves");

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ActiveProject activeProject;

    WaveAuthoringIntegrationTest(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired ActiveProject activeProject) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.activeProject = activeProject;
    }

    private HttpHeaders asAdministrator() {
        IssuedTokens tokens =
                authenticate.authenticate(
                        activeProject.id(), "admin@example.test", "correct-horse-battery-staple");
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(tokens.accessToken());
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private String sample(String name) throws Exception {
        return Files.readString(SAMPLES.resolve(name));
    }

    private ResponseEntity<String> post(String path, String body, HttpHeaders headers) {
        return rest.exchange(
                "http://localhost:" + port + path,
                HttpMethod.POST,
                new HttpEntity<>(body, headers),
                String.class);
    }

    private ResponseEntity<String> get(String path, HttpHeaders headers) {
        return rest.exchange(
                "http://localhost:" + port + path,
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);
    }

    @Test
    void a_demo_wave_can_be_authored_read_back_byte_identical_and_published() throws Exception {
        HttpHeaders headers = asAdministrator();
        String document = sample("demo_first_steps.json");

        ResponseEntity<String> created = post("/api/v1/admin/waves", document, headers);
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(created.getBody()).contains("\"id\":\"demo_first_steps\"").contains("\"published\":false");

        ResponseEntity<String> raw = get("/api/v1/admin/waves/demo_first_steps", headers);
        assertThat(raw.getBody())
                .as("the stored document must be the bytes that were sent")
                .isEqualTo(document);

        assertThat(post("/api/v1/admin/waves/demo_first_steps/publish", "", headers).getBody())
                .contains("\"published\":true");
    }

    @Test
    void a_document_that_does_not_satisfy_the_schema_is_refused_with_pointers() {
        ResponseEntity<String> response =
                post("/api/v1/admin/waves", "{\"id\":\"broken\"}", asAdministrator());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(response.getBody())
                .contains("violations")
                .contains("pointer")
                .as("an editor highlights fields by pointer, so they have to be pointers")
                .contains("/");
    }

    @Test
    void two_waves_may_not_share_an_order() throws Exception {
        HttpHeaders headers = asAdministrator();
        post("/api/v1/admin/waves", sample("demo_first_steps.json"), headers);

        // demo_first_steps is order 0; re-submitting it under a different id collides.
        String clash = sample("demo_first_steps.json").replace("demo_first_steps", "clashing_wave");
        ResponseEntity<String> response = post("/api/v1/admin/waves", clash, headers);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(response.getBody()).contains("/progression_config/order");
    }

    @Test
    void the_schema_version_is_stamped_when_a_document_omits_it() throws Exception {
        HttpHeaders headers = asAdministrator();
        String withoutVersion =
                sample("demo_crossfire.json").replaceFirst("\\s*\"schema_version\"\\s*:\\s*1,", "");

        post("/api/v1/admin/waves", withoutVersion, headers);

        assertThat(get("/api/v1/admin/waves/demo_crossfire", headers).getBody())
                .as("the one path allowed to change the bytes, and it must actually change them")
                .contains("\"schema_version\":1");
    }
}
