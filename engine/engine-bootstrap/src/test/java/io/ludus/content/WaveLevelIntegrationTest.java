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
 * Assembling a level and playing it, over HTTP.
 *
 * <p>The interesting assertions are the two places the authoring view and the player's view are
 * deliberately different: a draft member is listed to an editor and absent for a client, and a
 * project with no active level is a {@code 404} rather than an empty level.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class WaveLevelIntegrationTest {

    private static final Path SAMPLES = Path.of("..", "..", "samples", "waves");

    @LocalServerPort
    int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final ActiveProject activeProject;

    WaveLevelIntegrationTest(
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

    private ResponseEntity<String> anonymous(String path, String ifNoneMatch) {
        HttpHeaders headers = new HttpHeaders();
        if (ifNoneMatch != null) {
            headers.set(HttpHeaders.IF_NONE_MATCH, ifNoneMatch);
        }
        return rest.exchange(url(path), HttpMethod.GET, new HttpEntity<>(headers), String.class);
    }

    private ResponseEntity<String> asAdmin(String path, HttpMethod method, String body) {
        return rest.exchange(
                url(path), method, new HttpEntity<>(body, asAdministrator()), String.class);
    }

    /** Authors a wave from a sample, and publishes it only if asked. */
    private String wave(String sampleFile, boolean publish) throws Exception {
        String document = Files.readString(SAMPLES.resolve(sampleFile));
        asAdmin("/api/v1/admin/waves", HttpMethod.POST, document);
        String id = sampleFile.replace(".json", "");
        if (publish) {
            asAdmin("/api/v1/admin/waves/" + id + "/publish", HttpMethod.POST, "");
        }
        return id;
    }

    private String idOf(ResponseEntity<String> response) {
        return response.getBody().replaceAll(".*\"id\":\"([^\"]+)\".*", "$1");
    }

    // ------------------------------------------------------------------ the two views

    @Test
    void a_client_gets_the_published_members_and_an_editor_is_told_which_ones_they_are()
            throws Exception {
        String published = wave("demo_first_steps.json", true);
        String draft = wave("demo_pressure.json", false);

        ResponseEntity<String> created =
                asAdmin(
                        "/api/v1/admin/wave-levels",
                        HttpMethod.POST,
                        "{\"name\":\"Act One\",\"waves\":[\"" + published + "\",\"" + draft + "\"]}");
        assertThat(created.getStatusCode()).isEqualTo(HttpStatus.CREATED);

        assertThat(created.getBody())
                .as("the editor sees both members, and which of them players will not receive")
                .contains("\"waveId\":\"" + published + "\",\"published\":true")
                .contains("\"waveId\":\"" + draft + "\",\"published\":false");

        asAdmin("/api/v1/admin/wave-levels/" + idOf(created) + "/activate", HttpMethod.POST, "");

        ResponseEntity<String> playable = anonymous("/api/v1/public/wave-levels/active", null);
        assertThat(playable.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(playable.getBody())
                .as("the draft member is absent for a client, not present-but-unfetchable")
                .contains(published)
                .doesNotContain(draft);
    }

    /**
     * Reaches the no-active-level state rather than assuming it.
     *
     * <p>The first draft of this asserted the 404 on a fresh project and passed alone and failed in
     * the suite, because these methods share one context and one schema and another test had
     * activated something. Deleting the active level is both a way to get there deterministically
     * and the more interesting assertion: the activation row goes with the level, by foreign key,
     * so the project is left with nothing active rather than a pointer to something gone.
     */
    @Test
    void deleting_the_active_level_leaves_a_404_rather_than_a_dangling_pointer() throws Exception {
        String published = wave("demo_crossfire.json", true);
        ResponseEntity<String> created =
                asAdmin(
                        "/api/v1/admin/wave-levels",
                        HttpMethod.POST,
                        "{\"name\":\"Doomed\",\"waves\":[\"" + published + "\"]}");
        String levelId = idOf(created);
        asAdmin("/api/v1/admin/wave-levels/" + levelId + "/activate", HttpMethod.POST, "");

        assertThat(anonymous("/api/v1/public/wave-levels/active", null).getStatusCode())
                .isEqualTo(HttpStatus.OK);

        assertThat(asAdmin("/api/v1/admin/wave-levels/" + levelId, HttpMethod.DELETE, null)
                        .getStatusCode())
                .isEqualTo(HttpStatus.NO_CONTENT);

        assertThat(anonymous("/api/v1/public/wave-levels/active", null).getStatusCode())
                .as("a client must be able to tell 'nothing chosen' from 'chosen and empty'")
                .isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void the_active_level_carries_an_etag_that_answers_304() throws Exception {
        String published = wave("demo_first_steps.json", true);
        ResponseEntity<String> created =
                asAdmin(
                        "/api/v1/admin/wave-levels",
                        HttpMethod.POST,
                        "{\"name\":\"Act One\",\"waves\":[\"" + published + "\"]}");
        asAdmin("/api/v1/admin/wave-levels/" + idOf(created) + "/activate", HttpMethod.POST, "");

        String etag = anonymous("/api/v1/public/wave-levels/active", null).getHeaders().getETag();
        assertThat(etag).isNotBlank();

        assertThat(anonymous("/api/v1/public/wave-levels/active", etag).getStatusCode())
                .isEqualTo(HttpStatus.NOT_MODIFIED);
    }

    @Test
    void renaming_the_level_moves_its_etag() throws Exception {
        String published = wave("demo_first_steps.json", true);
        ResponseEntity<String> created =
                asAdmin(
                        "/api/v1/admin/wave-levels",
                        HttpMethod.POST,
                        "{\"name\":\"Act One\",\"waves\":[\"" + published + "\"]}");
        String levelId = idOf(created);
        asAdmin("/api/v1/admin/wave-levels/" + levelId + "/activate", HttpMethod.POST, "");

        String before = anonymous("/api/v1/public/wave-levels/active", null).getHeaders().getETag();

        asAdmin(
                "/api/v1/admin/wave-levels/" + levelId,
                HttpMethod.PUT,
                "{\"name\":\"Act Two\",\"waves\":[\"" + published + "\"]}");

        assertThat(anonymous("/api/v1/public/wave-levels/active", null).getHeaders().getETag())
                .as("the ETag covers the level itself, not only its members")
                .isNotEqualTo(before);
    }

    @Test
    void a_level_naming_a_wave_that_does_not_exist_is_a_422_at_the_index_that_named_it() {
        ResponseEntity<String> refused =
                asAdmin(
                        "/api/v1/admin/wave-levels",
                        HttpMethod.POST,
                        "{\"name\":\"Act One\",\"waves\":[\"ghost\"]}");

        assertThat(refused.getStatusCode()).isEqualTo(HttpStatus.UNPROCESSABLE_ENTITY);
        assertThat(refused.getBody()).contains("/waves/0");
    }

    @Test
    void an_unknown_level_is_a_404_whether_or_not_the_id_is_even_an_id() {
        assertThat(
                        asAdmin(
                                        "/api/v1/admin/wave-levels/"
                                                + java.util.UUID.randomUUID(),
                                        HttpMethod.GET,
                                        null)
                                .getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(asAdmin("/api/v1/admin/wave-levels/not-a-uuid", HttpMethod.GET, null).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
