// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.identity;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.application.identity.AdministratorSeeding;
import io.ludus.application.identity.ApiKeys;
import io.ludus.application.identity.AuthenticateUser;
import io.ludus.application.identity.IssuedTokens;
import io.ludus.application.identity.port.out.PasswordHasher;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.application.project.port.in.ActiveProject;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import java.time.Clock;
import java.util.List;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

/**
 * Who may call what, stated as a table and checked against the running application.
 *
 * <p>The roadmap names the failure this exists to prevent: an admin check copy-pasted into eight
 * route files, none of which actually verified that the user was an admin. Eight copies of a rule
 * is eight chances to get it wrong and no single place to read the answer. Here the rule lives in
 * one filter chain, and this table is the only description of what it should do.
 *
 * <p>Adding an endpoint without adding a row does not fail — nothing can force that. What this
 * does give is one file where the whole policy is visible, so a wrong answer is a diff rather
 * than an archaeology exercise.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class AuthorisationMatrixTest {

    @LocalServerPort int port;

    private final TestRestTemplate rest;
    private final AuthenticateUser authenticate;
    private final AdministratorSeeding seeding;
    private final ActiveProject activeProject;
    private final UserRepository users;
    private final PasswordHasher passwords;
    private final ApiKeys apiKeys;
    private final Clock clock;

    AuthorisationMatrixTest(
            @Autowired TestRestTemplate rest,
            @Autowired AuthenticateUser authenticate,
            @Autowired AdministratorSeeding seeding,
            @Autowired ActiveProject activeProject,
            @Autowired UserRepository users,
            @Autowired PasswordHasher passwords,
            @Autowired ApiKeys apiKeys,
            @Autowired Clock clock) {
        this.rest = rest;
        this.authenticate = authenticate;
        this.seeding = seeding;
        this.activeProject = activeProject;
        this.users = users;
        this.passwords = passwords;
        this.apiKeys = apiKeys;
        this.clock = clock;
    }

    private static final String ADMIN_EMAIL = "admin@example.test";
    private static final String ADMIN_PASSWORD = "correct-horse-battery-staple";
    private static final String EDITOR_EMAIL = "editor@example.test";
    private static final String VIEWER_EMAIL = "viewer@example.test";
    private static final String PASSWORD = "another-perfectly-fine-password";

    @BeforeEach
    void ensureTheCastExists() {
        // The administrator is seeded at startup by the runner; the other two are made here.
        seeding.seed(activeProject.id(), ADMIN_EMAIL, ADMIN_PASSWORD);
        ensure(EDITOR_EMAIL, Role.EDITOR);
        ensure(VIEWER_EMAIL, Role.VIEWER);
    }

    private void ensure(String email, Role role) {
        if (users.findByEmail(activeProject.id(), new EmailAddress(email)).isEmpty()) {
            users.save(
                    User.create(
                            activeProject.id(),
                            new EmailAddress(email),
                            passwords.hash(PASSWORD),
                            role,
                            clock.instant()));
        }
    }

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private String bearerFor(String email, String password) {
        IssuedTokens tokens = authenticate.authenticate(activeProject.id(), email, password);
        return "Bearer " + tokens.accessToken();
    }

    private ResponseEntity<String> get(String path, HttpHeaders headers) {
        return rest.exchange(
                url(path), HttpMethod.GET, new HttpEntity<>(headers), String.class);
    }

    private HttpHeaders bearer(String value) {
        HttpHeaders headers = new HttpHeaders();
        headers.set(HttpHeaders.AUTHORIZATION, value);
        return headers;
    }

    // ---------------------------------------------------------------- the table

    static Stream<Arguments> theMatrix() {
        return Stream.of(
                Arguments.of("anonymous", "/api/v1/me", HttpStatus.UNAUTHORIZED),
                Arguments.of("anonymous", "/api/v1/admin/api-keys", HttpStatus.UNAUTHORIZED),
                Arguments.of("anonymous", "/api/v1/anything", HttpStatus.UNAUTHORIZED),
                Arguments.of("viewer", "/api/v1/me", HttpStatus.OK),
                Arguments.of("viewer", "/api/v1/admin/api-keys", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/me", HttpStatus.OK),
                Arguments.of("editor", "/api/v1/admin/api-keys", HttpStatus.FORBIDDEN),
                Arguments.of("admin", "/api/v1/me", HttpStatus.OK),
                Arguments.of("admin", "/api/v1/admin/api-keys", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/me", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/admin/api-keys", HttpStatus.FORBIDDEN),

                // Authoring content is what the EDITOR role exists for, and it lives under the
                // same /admin prefix as key management. Two matchers, and the narrower one has to
                // be listed first or it is shadowed -- which is precisely the mistake these rows
                // exist to catch.
                Arguments.of("anonymous", "/api/v1/admin/waves", HttpStatus.UNAUTHORIZED),
                Arguments.of("viewer", "/api/v1/admin/waves", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/admin/waves", HttpStatus.OK),
                Arguments.of("admin", "/api/v1/admin/waves", HttpStatus.OK),
                // A key ends up in a shipped game binary. It must never be able to author.
                Arguments.of("api-key", "/api/v1/admin/waves", HttpStatus.FORBIDDEN),

                // Levels are authoring too, and got their own matcher entry rather than being
                // assumed covered. "/api/v1/admin/waves/**" does not match "/api/v1/admin/
                // wave-levels" -- a hyphen is not a slash -- so without these rows a new editor
                // route would silently have landed under the ADMIN-only matcher instead.
                Arguments.of("anonymous", "/api/v1/admin/wave-levels", HttpStatus.UNAUTHORIZED),
                Arguments.of("viewer", "/api/v1/admin/wave-levels", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/admin/wave-levels", HttpStatus.OK),
                Arguments.of("admin", "/api/v1/admin/wave-levels", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/admin/wave-levels", HttpStatus.FORBIDDEN),

                // Application configuration is edited by the same people who edit content.
                Arguments.of("anonymous", "/api/v1/admin/app-config", HttpStatus.UNAUTHORIZED),
                Arguments.of("viewer", "/api/v1/admin/app-config", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/admin/app-config", HttpStatus.OK),
                Arguments.of("admin", "/api/v1/admin/app-config", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/admin/app-config", HttpStatus.FORBIDDEN),

                // Published content is what every copy of the game downloads. It is public by
                // definition, so anonymous reaches it -- and that is the only thing anonymous
                // reaches. These rows are what stops the permitAll matcher widening by accident.
                Arguments.of("anonymous", "/api/v1/public/status", HttpStatus.OK),
                Arguments.of("anonymous", "/api/v1/public/waves", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/public/waves", HttpStatus.OK),
                Arguments.of("viewer", "/api/v1/public/waves", HttpStatus.OK),
                Arguments.of("admin", "/api/v1/public/waves", HttpStatus.OK),
                // The active level, with no level chosen: a 404 rather than a 401, which is how
                // this row proves the route was reached rather than refused.
                Arguments.of("anonymous", "/api/v1/public/wave-levels/active", HttpStatus.NOT_FOUND),
                Arguments.of("api-key", "/api/v1/public/wave-levels/active", HttpStatus.NOT_FOUND),
                // Configuration always answers, even unconfigured: an empty object, never a 404.
                Arguments.of("anonymous", "/api/v1/public/app-config", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/public/app-config", HttpStatus.OK),

                // A player's own state needs a player session token. None of the credentials in
                // this matrix is one, so every row here is a refusal -- which is the point: an
                // API key that could reach these routes would let anyone who unpacked the game
                // write any player's state.
                Arguments.of("anonymous", "/api/v1/player/me", HttpStatus.UNAUTHORIZED),
                Arguments.of("api-key", "/api/v1/player/me", HttpStatus.FORBIDDEN),
                Arguments.of("viewer", "/api/v1/player/me", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/player/me", HttpStatus.FORBIDDEN),
                // Not even an administrator. There is no route by which one acts as a player, and
                // an admin token reaching /player/me would be one.
                Arguments.of("admin", "/api/v1/player/me", HttpStatus.FORBIDDEN),

                // Minting a player session needs an API key, unlike the rest of /public. A GET is
                // used here because this matrix only issues GETs; it proves the matcher is reached
                // rather than shadowed by the permitAll below it.
                Arguments.of("anonymous", "/api/v1/anything-unnamed", HttpStatus.UNAUTHORIZED),

                // A player's wallet, read by themselves only. Every credential here is refused.
                Arguments.of("api-key", "/api/v1/player/me/wallet", HttpStatus.FORBIDDEN),
                Arguments.of("admin", "/api/v1/player/me/wallet", HttpStatus.FORBIDDEN),

                // Awarding currency and editing the XP curve are an editor's job, and deliberately
                // not reachable by a credential that ships inside the game.
                Arguments.of("anonymous", "/api/v1/admin/players", HttpStatus.UNAUTHORIZED),
                Arguments.of("api-key", "/api/v1/admin/players", HttpStatus.FORBIDDEN),
                Arguments.of("viewer", "/api/v1/admin/players", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/admin/players", HttpStatus.OK),
                Arguments.of("admin", "/api/v1/admin/players", HttpStatus.OK),
                Arguments.of("api-key", "/api/v1/admin/xp-curve", HttpStatus.FORBIDDEN),
                Arguments.of("editor", "/api/v1/admin/xp-curve", HttpStatus.OK));
    }

    @ParameterizedTest(name = "{0} calling {1} gets {2}")
    @MethodSource("theMatrix")
    void the_policy_is_what_the_table_says(String who, String path, HttpStatus expected) {
        HttpHeaders headers = headersFor(who);

        assertThat(get(path, headers).getStatusCode()).isEqualTo(expected);
    }

    private HttpHeaders headersFor(String who) {
        return switch (who) {
            case "anonymous" -> new HttpHeaders();
            case "viewer" -> bearer(bearerFor(VIEWER_EMAIL, PASSWORD));
            case "editor" -> bearer(bearerFor(EDITOR_EMAIL, PASSWORD));
            case "admin" -> bearer(bearerFor(ADMIN_EMAIL, ADMIN_PASSWORD));
            case "api-key" -> {
                HttpHeaders headers = new HttpHeaders();
                headers.set("X-API-Key", apiKeys.issue(activeProject.id(), "test").plaintext());
                yield headers;
            }
            default -> throw new IllegalArgumentException("unknown caller " + who);
        };
    }

    // ------------------------------------------------------- things the table cannot say

    @Test
    void a_forged_token_authenticates_as_nobody() {
        String forged =
                "eyJhbGciOiJIUzI1NiJ9"
                        + ".eyJpc3MiOiJsdWR1cyIsInN1YiI6ImFkbWluIiwicm9sZSI6IkFETUlOIn0"
                        + ".this-signature-is-not-real";

        assertThat(get("/api/v1/me", bearer("Bearer " + forged)).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void a_revoked_api_key_stops_working_immediately() {
        ApiKeys.NewApiKey issued = apiKeys.issue(activeProject.id(), "to-be-revoked");
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-API-Key", issued.plaintext());

        assertThat(get("/api/v1/me", headers).getStatusCode()).isEqualTo(HttpStatus.OK);

        apiKeys.revoke(activeProject.id(), issued.key().id());

        assertThat(get("/api/v1/me", headers).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void an_api_key_reports_itself_as_a_viewer_and_not_as_a_person() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-API-Key", apiKeys.issue(activeProject.id(), "reporting").plaintext());

        assertThat(get("/api/v1/me", headers).getBody())
                .contains("\"kind\":\"API_KEY\"")
                .contains("\"role\":\"VIEWER\"");
    }

    @Test
    void the_operational_endpoints_stay_open_and_the_docs_stay_readable() {
        List<String> open = List.of("/actuator/health", "/actuator/prometheus", "/api-docs");

        assertThat(open)
                .allSatisfy(
                        path ->
                                assertThat(get(path, new HttpHeaders()).getStatusCode())
                                        .as(path)
                                        .isEqualTo(HttpStatus.OK));
    }
}
