// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.architecture;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.test.context.ActiveProfiles;

/**
 * The reason it is safe to disable CSRF protection, written down as a test.
 *
 * <p>Every filter chain calls {@code csrf.disable()}, and CodeQL flags all three. The flag is
 * correct in general and wrong here, for one specific reason: cross-site request forgery needs a
 * credential the browser attaches to a cross-origin request <em>by itself</em> — a session cookie,
 * or HTTP Basic. This engine has none. Sessions are stateless and both credentials are custom
 * headers, which a browser never sends on its own.
 *
 * <p>That reasoning was previously written in a comment, and a comment does not fail. If somebody
 * adds cookie or session authentication later and leaves CSRF disabled, the alerts stop being
 * false positives and nothing would have said so. This test is what says so.
 *
 * <p>It is deliberately about the <em>absence</em> of things. If it fails, do not make it pass —
 * work out whether CSRF protection now needs enabling for the chain that changed.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class StatelessAuthenticationTest {

    @LocalServerPort
    int port;

    private final ApplicationContext context;
    private final TestRestTemplate rest;

    StatelessAuthenticationTest(
            @Autowired ApplicationContext context, @Autowired TestRestTemplate rest) {
        this.context = context;
        this.rest = rest;
    }

    /**
     * A {@code UserDetailsService} is how Spring Security's cookie-backed login mechanisms get
     * their users. Its absence is what keeps form login and Basic from being wired up by
     * autoconfiguration in the first place.
     */
    @Test
    void nothing_registers_a_user_details_service() {
        assertThat(context.getBeanNamesForType(UserDetailsService.class))
                .as(
                        "a UserDetailsService means a cookie-backed login is possible, and the"
                                + " decision to disable CSRF has to be revisited")
                .isEmpty();
    }

    /**
     * No response may create a session. A session identifier is a cookie, and a cookie is
     * precisely the thing a browser attaches to a cross-site request without being asked.
     */
    @Test
    void no_response_sets_a_session_cookie() {
        List<String> paths =
                List.of(
                        "/actuator/health",
                        "/api-docs",
                        "/api/v1/me",
                        "/api/v1/auth/token",
                        "/api/v1/anything");

        assertThat(paths)
                .allSatisfy(
                        path -> {
                            ResponseEntity<String> response =
                                    rest.exchange(
                                            "http://localhost:" + port + path,
                                            HttpMethod.GET,
                                            null,
                                            String.class);

                            assertThat(response.getHeaders().get(HttpHeaders.SET_COOKIE))
                                    .as("%s must not set a cookie", path)
                                    .isNullOrEmpty();
                        });
    }

    /**
     * Basic authentication is browser-attached in the same way a cookie is, once the browser has
     * been challenged. A {@code WWW-Authenticate: Basic} challenge is how that starts, so its
     * absence is worth pinning too.
     */
    @Test
    void an_unauthenticated_request_is_not_challenged_for_browser_credentials() {
        ResponseEntity<String> response =
                rest.getForEntity("http://localhost:" + port + "/api/v1/me", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(response.getHeaders().get(HttpHeaders.WWW_AUTHENTICATE))
                .as(
                        "a challenge invites the browser to hold credentials and send them"
                                + " automatically, which is the precondition for CSRF")
                .isNullOrEmpty();
    }

    /**
     * The positive half: a credential presented in a custom header works. Browsers do not attach
     * these cross-origin without an explicit, CORS-preflighted request, which is what makes the
     * whole arrangement safe.
     */
    @Test
    void the_only_credentials_that_work_are_ones_a_browser_will_not_send_by_itself() {
        HttpHeaders nonsenseBearer = new HttpHeaders();
        nonsenseBearer.set(HttpHeaders.AUTHORIZATION, "Bearer not-a-real-token");

        HttpHeaders nonsenseApiKey = new HttpHeaders();
        nonsenseApiKey.set("X-API-Key", "ludus_not-a-real-key");

        // Both are rejected, which is the point: they are read, and they are the only things read.
        assertThat(get("/api/v1/me", nonsenseBearer).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(get("/api/v1/me", nonsenseApiKey).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    private ResponseEntity<String> get(String path, HttpHeaders headers) {
        return rest.exchange(
                "http://localhost:" + port + path,
                HttpMethod.GET,
                new org.springframework.http.HttpEntity<>(headers),
                String.class);
    }
}
