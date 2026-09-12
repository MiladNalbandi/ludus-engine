// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.player;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.identity.ApiKeys;
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
 * The player credential, over HTTP.
 *
 * <p>This is where the answer to #10's "a game client can read and write player state with an API
 * key" is checked. It cannot, and these tests are what make that true rather than intended: a key
 * mints a session and reaches nothing else, and the token it mints acts as exactly one player.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class PlayerSessionIntegrationTest {

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ApiKeys apiKeys;
    private final ActiveProject activeProject;

    PlayerSessionIntegrationTest(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired ApiKeys apiKeys,
            @Autowired ActiveProject activeProject) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.apiKeys = apiKeys;
        this.activeProject = activeProject;
    }

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private String adminToken() {
        return authenticate
                .authenticate(activeProject.id(), "admin@example.test", "correct-horse-battery-staple")
                .accessToken();
    }

    /** A real key, minted the way an administrator would. */
    private String apiKey() {
        return apiKeys.issue(activeProject.id(), "player-session-test-" + System.nanoTime()).plaintext();
    }

    private HttpHeaders bearer(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(token);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    /** An API key travels in its own header, not as a bearer token. */
    private HttpHeaders keyHeader(String key) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-API-Key", key);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private ResponseEntity<String> startSession(String key, String externalId) {
        return rest.exchange(
                url("/api/v1/public/players/session"),
                HttpMethod.POST,
                new HttpEntity<>("{\"externalId\":\"" + externalId + "\"}", keyHeader(key)),
                String.class);
    }

    private String tokenFrom(ResponseEntity<String> session) {
        return session.getBody().replaceAll(".*\"token\":\"([^\"]+)\".*", "$1");
    }

    private String playerIdFrom(ResponseEntity<String> session) {
        return session.getBody().replaceAll(".*\"playerId\":\"([^\"]+)\".*", "$1");
    }

    // ------------------------------------------------------------------ the credential

    @Test
    void an_api_key_mints_a_session_and_the_token_acts_as_that_player() {
        ResponseEntity<String> session = startSession(apiKey(), "device-one");
        assertThat(session.getStatusCode()).isEqualTo(HttpStatus.OK);

        ResponseEntity<String> me =
                rest.exchange(
                        url("/api/v1/player/me"),
                        HttpMethod.GET,
                        new HttpEntity<>(bearer(tokenFrom(session))),
                        String.class);

        assertThat(me.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(me.getBody())
                .contains("\"externalId\":\"device-one\"")
                .contains(playerIdFrom(session));
    }

    @Test
    void starting_a_session_requires_a_key_even_though_the_rest_of_public_does_not() {
        HttpHeaders anonymous = new HttpHeaders();
        anonymous.setContentType(MediaType.APPLICATION_JSON);

        ResponseEntity<String> refused =
                rest.exchange(
                        url("/api/v1/public/players/session"),
                        HttpMethod.POST,
                        new HttpEntity<>("{\"externalId\":\"device-x\"}", anonymous),
                        String.class);

        assertThat(refused.getStatusCode())
                .as("minting a credential is not reading published content")
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void the_api_key_that_minted_the_session_cannot_itself_read_player_state() {
        String key = apiKey();
        startSession(key, "device-two");

        ResponseEntity<String> refused =
                rest.exchange(
                        url("/api/v1/player/me"),
                        HttpMethod.GET,
                        new HttpEntity<>(keyHeader(key)),
                        String.class);

        assertThat(refused.getStatusCode())
                .as("a key ships inside the binary; anything it can do is public")
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void an_administrators_token_cannot_act_as_a_player() {
        ResponseEntity<String> refused =
                rest.exchange(
                        url("/api/v1/player/me"),
                        HttpMethod.GET,
                        new HttpEntity<>(bearer(adminToken())),
                        String.class);

        assertThat(refused.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
    }

    @Test
    void a_player_token_cannot_reach_an_administrative_route() {
        String token = tokenFrom(startSession(apiKey(), "device-three"));

        // 403, not 401, and the difference is the engine's own documented one: the player token is
        // perfectly valid, so the problem is the role and not the credential. Pointing whoever is
        // debugging at their token would send them the wrong way.
        assertThat(
                        rest.exchange(
                                        url("/api/v1/admin/waves"),
                                        HttpMethod.GET,
                                        new HttpEntity<>(bearer(token)),
                                        String.class)
                                .getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);

        // Nor a route that merely requires a credential: the chain's fallback asks for a real role,
        // not just authentication, which is what keeps a player out of everything unnamed.
        assertThat(
                        rest.exchange(
                                        url("/api/v1/me"),
                                        HttpMethod.GET,
                                        new HttpEntity<>(bearer(token)),
                                        String.class)
                                .getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
    }

    // ------------------------------------------------------------------ the player

    @Test
    void a_retried_session_start_resolves_the_same_player() {
        String key = apiKey();

        String first = playerIdFrom(startSession(key, "device-retry"));
        String second = playerIdFrom(startSession(key, "device-retry"));

        assertThat(second)
                .as("a network blip must not strand the first player's progress")
                .isEqualTo(first);
    }

    @Test
    void a_player_can_set_and_clear_their_own_display_name() {
        String token = tokenFrom(startSession(apiKey(), "device-named"));

        ResponseEntity<String> named =
                rest.exchange(
                        url("/api/v1/player/me"),
                        HttpMethod.PATCH,
                        new HttpEntity<>("{\"displayName\":\"Alex\"}", bearer(token)),
                        String.class);

        assertThat(named.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(named.getBody()).contains("\"displayName\":\"Alex\"");

        ResponseEntity<String> cleared =
                rest.exchange(
                        url("/api/v1/player/me"),
                        HttpMethod.PATCH,
                        new HttpEntity<>("{\"displayName\":\"\"}", bearer(token)),
                        String.class);

        assertThat(cleared.getBody()).doesNotContain("\"displayName\":\"Alex\"");
    }

    @Test
    void a_session_without_an_identifier_is_refused() {
        assertThat(
                        rest.exchange(
                                        url("/api/v1/public/players/session"),
                                        HttpMethod.POST,
                                        new HttpEntity<>("{}", keyHeader(apiKey())),
                                        String.class)
                                .getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }
}
