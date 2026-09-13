// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.content;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.project.port.in.ActiveProject;
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
 * Application configuration over HTTP.
 *
 * <p>The two assertions worth the file: the bytes survive the round trip, because this document is
 * fetched by every client on every launch and its ETag is a hash of them; and an empty request body
 * is a {@code 422} rather than a {@code 500}.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class AppConfigIntegrationTest {

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ActiveProject activeProject;

    AppConfigIntegrationTest(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired ActiveProject activeProject) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.activeProject = activeProject;
    }

    private String url(String path) {
        return "http://localhost:" + port + path;
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

    private ResponseEntity<String> put(String body) {
        return rest.exchange(
                url("/api/v1/admin/app-config"),
                HttpMethod.PUT,
                new HttpEntity<>(body, asAdministrator()),
                String.class);
    }

    private ResponseEntity<String> anonymous(String ifNoneMatch) {
        HttpHeaders headers = new HttpHeaders();
        if (ifNoneMatch != null) {
            headers.set(HttpHeaders.IF_NONE_MATCH, ifNoneMatch);
        }
        return rest.exchange(
                url("/api/v1/public/app-config"),
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);
    }

    @Test
    void the_bytes_a_client_receives_are_the_bytes_an_editor_sent() {
        String awkward = "{\"spawnRate\":1.0,   \"z\":true,\n  \"a\":[1,2,3]}";

        assertThat(put(awkward).getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<String> served = anonymous(null);
        assertThat(served.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(served.getBody())
                .as("whitespace, key order and 1.0-versus-1 all survive, or the ETag moves for nothing")
                .isEqualTo(awkward);
    }

    @Test
    void the_config_is_cacheable_and_answers_304() {
        put("{\"difficulty\":\"normal\"}");

        String etag = anonymous(null).getHeaders().getETag();
        assertThat(etag).isNotBlank();

        assertThat(anonymous(etag).getStatusCode()).isEqualTo(HttpStatus.NOT_MODIFIED);
    }

    @Test
    void editing_the_config_moves_the_etag() {
        put("{\"difficulty\":\"normal\"}");
        String before = anonymous(null).getHeaders().getETag();

        put("{\"difficulty\":\"hard\"}");

        assertThat(anonymous(null).getHeaders().getETag()).isNotEqualTo(before);
    }

    @Test
    void an_empty_request_body_is_a_422_rather_than_a_500() {
        ResponseEntity<String> refused = put("");

        assertThat(refused.getStatusCode())
                .as("the caller sent nothing; that is their mistake to fix, not an engine failure")
                .isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
    }

    @Test
    void malformed_json_is_a_422_naming_where_it_stops_parsing() {
        ResponseEntity<String> refused = put("{\"difficulty\":}");

        assertThat(refused.getStatusCode()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(refused.getBody())
                .as("the parser's line and column are the only genuinely useful part of its message")
                .contains("line");
    }

    @Test
    void the_public_route_needs_no_credential_and_the_admin_route_does() {
        assertThat(anonymous(null).getStatusCode()).isEqualTo(HttpStatus.OK);

        assertThat(
                        rest.exchange(
                                        url("/api/v1/admin/app-config"),
                                        HttpMethod.GET,
                                        new HttpEntity<>(new HttpHeaders()),
                                        String.class)
                                .getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
