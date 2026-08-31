// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.content;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.identity.AuthenticateUser;
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
 * The client's whole story, over HTTP, with no credential.
 *
 * <p>The assertion this file exists for is {@link #the_status_hash_and_the_list_etag_are_the_same
 * one}. Everything else here is ordinary endpoint testing; that one is the guarantee the caching
 * design rests on, and it is the one that would be quietly untrue if the two signals were ever
 * computed separately.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class PublicContentIntegrationTest {

    private static final Path SAMPLES = Path.of("..", "..", "samples", "waves");

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ActiveProject activeProject;

    PublicContentIntegrationTest(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired ActiveProject activeProject) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.activeProject = activeProject;
    }

    // ------------------------------------------------------------------ helpers

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    /** No credential at all — the point of these routes. */
    private ResponseEntity<String> anonymous(String path, String ifNoneMatch) {
        HttpHeaders headers = new HttpHeaders();
        if (ifNoneMatch != null) {
            headers.set(HttpHeaders.IF_NONE_MATCH, ifNoneMatch);
        }
        return rest.exchange(url(path), HttpMethod.GET, new HttpEntity<>(headers), String.class);
    }

    private HttpHeaders asAdministrator() {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(
                authenticate
                        .authenticate(
                                activeProject.id(),
                                "admin@example.test",
                                "correct-horse-battery-staple")
                        .accessToken());
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private String publish(String sampleFile) throws Exception {
        HttpHeaders headers = asAdministrator();
        String document = Files.readString(SAMPLES.resolve(sampleFile));
        rest.exchange(
                url("/api/v1/admin/waves"),
                HttpMethod.POST,
                new HttpEntity<>(document, headers),
                String.class);
        String id = sampleFile.replace(".json", "");
        rest.exchange(
                url("/api/v1/admin/waves/" + id + "/publish"),
                HttpMethod.POST,
                new HttpEntity<>("", headers),
                String.class);
        return document;
    }

    // ------------------------------------------------------------------ the guarantee

    /**
     * If these two ever differ, a client is told "something changed" by the poll, refetches, and is
     * handed a 304 validated against the other signal — or the reverse, told nothing changed while
     * a cache holds stale bytes. Neither is visible from either side alone.
     */
    @Test
    void the_status_hash_and_the_list_etag_are_the_same_one() throws Exception {
        publish("demo_first_steps.json");

        String statusBody = anonymous("/api/v1/public/status", null).getBody();
        String listEtag = anonymous("/api/v1/public/waves", null).getHeaders().getETag();

        assertThat(listEtag)
                .as("the list ETag must BE the status hash, not merely track it")
                .isEqualTo("\"" + extractHash(statusBody) + "\"");
    }

    private String extractHash(String statusBody) {
        return statusBody.replaceAll(".*\"contentHash\"\\s*:\\s*\"([^\"]+)\".*", "$1");
    }

    // ------------------------------------------------------------------ caching

    @Test
    void re_requesting_the_list_with_its_etag_gets_304() throws Exception {
        publish("demo_first_steps.json");

        String etag = anonymous("/api/v1/public/waves", null).getHeaders().getETag();

        ResponseEntity<String> again = anonymous("/api/v1/public/waves", etag);
        assertThat(again.getStatusCode()).isEqualTo(HttpStatus.NOT_MODIFIED);
        assertThat(again.getBody()).isNull();
    }

    @Test
    void re_requesting_a_document_with_its_etag_gets_304() throws Exception {
        publish("demo_first_steps.json");

        String etag =
                anonymous("/api/v1/public/waves/demo_first_steps/raw", null)
                        .getHeaders()
                        .getETag();

        assertThat(anonymous("/api/v1/public/waves/demo_first_steps/raw", etag).getStatusCode())
                .isEqualTo(HttpStatus.NOT_MODIFIED);
    }

    /** A cache adds the weak marker on its own; refusing it would silently disable caching. */
    @Test
    void a_weak_validator_from_a_cache_is_honoured() throws Exception {
        publish("demo_first_steps.json");
        String etag = anonymous("/api/v1/public/waves", null).getHeaders().getETag();

        assertThat(anonymous("/api/v1/public/waves", "W/" + etag).getStatusCode())
                .isEqualTo(HttpStatus.NOT_MODIFIED);
        assertThat(anonymous("/api/v1/public/waves", "*").getStatusCode())
                .isEqualTo(HttpStatus.NOT_MODIFIED);
    }

    @Test
    void a_stale_etag_gets_the_content() throws Exception {
        publish("demo_first_steps.json");

        ResponseEntity<String> response =
                anonymous("/api/v1/public/waves", "\"sha256:something-else\"");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).contains("demo_first_steps");
    }

    /** The poll must never be cached; an answer to "did anything change" can go stale. */
    @Test
    void the_status_poll_forbids_caching() {
        assertThat(anonymous("/api/v1/public/status", null).getHeaders().getCacheControl())
                .contains("no-store");
    }

    @Test
    void publishing_something_new_moves_both_signals() throws Exception {
        publish("demo_first_steps.json");
        String before = anonymous("/api/v1/public/waves", null).getHeaders().getETag();

        publish("demo_crossfire.json");
        String after = anonymous("/api/v1/public/waves", null).getHeaders().getETag();

        assertThat(after).isNotEqualTo(before);
        assertThat(anonymous("/api/v1/public/waves", before).getStatusCode())
                .isEqualTo(HttpStatus.OK);
    }

    // ------------------------------------------------------------------ what is visible

    @Test
    void a_document_is_served_as_the_bytes_it_was_stored_as() throws Exception {
        String document = publish("demo_first_steps.json");

        assertThat(anonymous("/api/v1/public/waves/demo_first_steps/raw", null).getBody())
                .isEqualTo(document);
    }

    /**
     * A draft is a 404, not a 403. Editing content must not affect players, and a client able to
     * tell "exists but hidden" from "does not exist" has been told about unreleased content.
     */
    @Test
    void a_draft_does_not_exist_as_far_as_a_client_is_concerned() throws Exception {
        HttpHeaders headers = asAdministrator();
        rest.exchange(
                url("/api/v1/admin/waves"),
                HttpMethod.POST,
                new HttpEntity<>(Files.readString(SAMPLES.resolve("demo_pressure.json")), headers),
                String.class);

        assertThat(anonymous("/api/v1/public/waves/demo_pressure", null).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(anonymous("/api/v1/public/waves/demo_pressure/raw", null).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(anonymous("/api/v1/public/waves", null).getBody())
                .doesNotContain("demo_pressure");
    }

    @Test
    void unpublishing_removes_it_again() throws Exception {
        publish("demo_first_steps.json");
        assertThat(anonymous("/api/v1/public/waves/demo_first_steps", null).getStatusCode())
                .isEqualTo(HttpStatus.OK);

        rest.exchange(
                url("/api/v1/admin/waves/demo_first_steps/unpublish"),
                HttpMethod.POST,
                new HttpEntity<>("", asAdministrator()),
                String.class);

        assertThat(anonymous("/api/v1/public/waves/demo_first_steps", null).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void something_that_never_existed_is_the_same_answer() {
        assertThat(anonymous("/api/v1/public/waves/no_such_wave", null).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(anonymous("/api/v1/public/waves/Not A Slug", null).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
