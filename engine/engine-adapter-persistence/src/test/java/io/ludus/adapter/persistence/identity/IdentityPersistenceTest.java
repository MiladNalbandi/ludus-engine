// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatException;

import io.ludus.adapter.persistence.project.ProjectRepositoryAdapter;
import io.ludus.application.identity.port.out.ApiKeyRepository;
import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.application.project.port.out.ProjectRepository;
import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.PasswordHash;
import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.Project;
import io.ludus.domain.project.ProjectId;
import io.ludus.domain.shared.Slug;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.context.annotation.Import;

/**
 * The identity tables, against the migrations that ship.
 *
 * <p>Two projects exist in every test here. A repository that ignores its project argument passes
 * every single-project test ever written, so the only way for these assertions to mean anything
 * is for there to be someone else's row to accidentally return.
 */
@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import({
    ProjectRepositoryAdapter.class,
    UserRepositoryAdapter.class,
    RefreshTokenRepositoryAdapter.class,
    ApiKeyRepositoryAdapter.class
})
class IdentityPersistenceTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");

    @Autowired private ProjectRepository projects;
    @Autowired private UserRepository users;
    @Autowired private RefreshTokenRepository refreshTokens;
    @Autowired private ApiKeyRepository apiKeys;
    @Autowired private TestEntityManager entityManager;

    private ProjectId mine;
    private ProjectId theirs;

    @BeforeEach
    void twoProjects() {
        mine = projects.save(Project.create(new Slug("mine"), "Mine", NOW)).id();
        theirs = projects.save(Project.create(new Slug("theirs"), "Theirs", NOW)).id();
        reachTheDatabase();
    }

    private void reachTheDatabase() {
        entityManager.flush();
        entityManager.clear();
    }

    private User aUser(ProjectId project, String email) {
        return users.save(
                User.create(
                        project,
                        new EmailAddress(email),
                        new PasswordHash("$2a$10$notarealhashbutlongenough"),
                        Role.EDITOR,
                        NOW));
    }

    @Test
    void a_user_round_trips_with_every_field_intact() {
        User saved = aUser(mine, "ada@example.com");
        reachTheDatabase();

        assertThat(users.findById(mine, saved.id())).contains(saved);
        assertThat(users.findByEmail(mine, new EmailAddress("ada@example.com"))).contains(saved);
    }

    @Test
    void a_user_is_invisible_from_another_project() {
        User saved = aUser(mine, "ada@example.com");
        reachTheDatabase();

        assertThat(users.findById(theirs, saved.id())).isEmpty();
        assertThat(users.findByEmail(theirs, new EmailAddress("ada@example.com"))).isEmpty();
        assertThat(users.countIn(theirs)).isZero();
    }

    /** Two projects are allowed the same address; they are different people. */
    @Test
    void the_same_address_may_exist_once_in_each_project() {
        aUser(mine, "ada@example.com");
        aUser(theirs, "ada@example.com");
        reachTheDatabase();

        assertThat(users.countIn(mine)).isEqualTo(1);
        assertThat(users.countIn(theirs)).isEqualTo(1);
    }

    @Test
    void the_same_address_cannot_exist_twice_in_one_project() {
        aUser(mine, "ada@example.com");
        reachTheDatabase();
        aUser(mine, "ada@example.com");

        assertThatException()
                .as("uq_app_user_project_email must reject the second insert")
                .isThrownBy(() -> entityManager.flush());
    }

    @Test
    void a_refresh_token_is_found_by_its_digest_and_only_within_its_project() {
        User ada = aUser(mine, "ada@example.com");
        SecretDigest digest = new SecretDigest("a".repeat(64));
        refreshTokens.save(
                RefreshToken.issue(mine, ada.id(), digest, NOW, NOW.plusSeconds(3600)));
        reachTheDatabase();

        assertThat(refreshTokens.findByDigest(mine, digest)).isPresent();
        assertThat(refreshTokens.findByDigest(theirs, digest)).isEmpty();
    }

    @Test
    void signing_out_revokes_only_that_users_tokens_in_that_project() {
        User ada = aUser(mine, "ada@example.com");
        User grace = aUser(mine, "grace@example.com");
        SecretDigest adasLaptop = new SecretDigest("a".repeat(64));
        SecretDigest adasPhone = new SecretDigest("b".repeat(64));
        SecretDigest graces = new SecretDigest("c".repeat(64));

        refreshTokens.save(RefreshToken.issue(mine, ada.id(), adasLaptop, NOW, NOW.plusSeconds(60)));
        refreshTokens.save(RefreshToken.issue(mine, ada.id(), adasPhone, NOW, NOW.plusSeconds(60)));
        refreshTokens.save(RefreshToken.issue(mine, grace.id(), graces, NOW, NOW.plusSeconds(60)));
        reachTheDatabase();

        int revoked = refreshTokens.revokeAllFor(mine, ada.id(), NOW.plusSeconds(5));
        reachTheDatabase();

        assertThat(revoked).isEqualTo(2);
        assertThat(refreshTokens.findByDigest(mine, adasLaptop).orElseThrow().revokedAt())
                .isNotNull();
        assertThat(refreshTokens.findByDigest(mine, graces).orElseThrow().revokedAt())
                .as("another user's session must not be collateral damage")
                .isNull();
    }

    @Test
    void an_api_key_is_found_by_digest_and_only_within_its_project() {
        SecretDigest digest = new SecretDigest("d".repeat(64));
        ApiKey key =
                apiKeys.save(
                        ApiKey.create(mine, "android", "ludus_ab", digest, Role.VIEWER, NOW));
        reachTheDatabase();

        assertThat(apiKeys.findByDigest(mine, digest)).contains(key);
        assertThat(apiKeys.findByDigest(theirs, digest)).isEmpty();
        assertThat(apiKeys.findById(theirs, key.id())).isEmpty();
        assertThat(apiKeys.listIn(theirs)).isEmpty();
        assertThat(apiKeys.listIn(mine)).containsExactly(key);
    }

    @Test
    void revocation_is_stored_rather_than_the_row_being_removed() {
        SecretDigest digest = new SecretDigest("e".repeat(64));
        ApiKey key =
                apiKeys.save(
                        ApiKey.create(mine, "android", "ludus_cd", digest, Role.VIEWER, NOW));
        apiKeys.save(key.revokedAt(NOW.plusSeconds(30)));
        reachTheDatabase();

        assertThat(apiKeys.listIn(mine))
                .singleElement()
                .satisfies(
                        stored -> {
                            assertThat(stored.isRevoked()).isTrue();
                            assertThat(stored.revokedAt()).isEqualTo(NOW.plusSeconds(30));
                        });
    }

    /** The database refuses a user that belongs to no project, whatever the application does. */
    @Test
    void a_user_cannot_reference_a_project_that_does_not_exist() {
        users.save(
                User.create(
                        ProjectId.random(),
                        new EmailAddress("nowhere@example.com"),
                        new PasswordHash("$2a$10$notarealhashbutlongenough"),
                        Role.VIEWER,
                        NOW));

        assertThatException()
                .as("fk_app_user_project must reject it")
                .isThrownBy(() -> entityManager.flush());
    }
}
