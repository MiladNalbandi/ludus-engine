// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.player;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.adapter.security.jwt.JwtAccessTokens;
import io.ludus.adapter.security.jwt.JwtProperties;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.PasswordHash;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

/**
 * The two kinds of token are signed with one secret and must never be accepted for each other.
 *
 * <p>Sharing the secret is a convenience — there is one party issuing and one verifying. Sharing an
 * <em>audience</em> would be a vulnerability: a player session token authorises writes to one
 * player's state, and an access token authorises administration. Without the {@code typ} claim the
 * two differ only in which claims they happen to carry, and a verifier that tolerated a missing
 * role would read a player as an administrator with no role — which is exactly the kind of
 * "defaults to something sensible" change somebody makes later in good faith.
 *
 * <p>This is the test that stops that being possible to do quietly.
 */
class TokenKindsAreNotInterchangeableTest {

    private static final Instant NOW = Instant.parse("2026-09-12T13:00:00Z");
    private static final ProjectId PROJECT = ProjectId.random();

    private final JwtProperties properties = properties();
    private final Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
    private final JwtAccessTokens accessTokens = new JwtAccessTokens(properties, clock);
    private final JwtPlayerTokens playerTokens = new JwtPlayerTokens(properties, clock);

    private static JwtProperties properties() {
        JwtProperties properties = new JwtProperties();
        // Long enough for HS256, which needs a 256-bit key.
        properties.setSecret("a-test-signing-secret-that-is-long-enough-for-hs256");
        properties.setIssuer("ludus-test");
        return properties;
    }

    private User administrator() {
        return new User(
                UserId.random(),
                PROJECT,
                new EmailAddress("admin@example.test"),
                new PasswordHash("$2a$10$notarealhashbutlongenoughtopass............."),
                Role.ADMIN,
                true,
                NOW);
    }

    private Player player() {
        return Player.firstSeen(PlayerId.random(), PROJECT, "device-abc", NOW);
    }

    @Test
    void a_player_token_does_not_authenticate_a_user() {
        String token = playerTokens.issue(player(), NOW, NOW.plus(Duration.ofHours(1)));

        assertThat(accessTokens.verify(token))
                .as("a player must not be readable as an administrator")
                .isEmpty();
    }

    @Test
    void a_user_token_does_not_authenticate_a_player() {
        String token = accessTokens.issue(administrator(), NOW, NOW.plus(Duration.ofMinutes(15)));

        assertThat(playerTokens.verify(token))
                .as("an administrator's token must not act as a player either")
                .isEmpty();
    }

    @Test
    void each_kind_verifies_its_own() {
        Player player = player();
        String playerToken = playerTokens.issue(player, NOW, NOW.plus(Duration.ofHours(1)));

        assertThat(playerTokens.verify(playerToken))
                .get()
                .satisfies(
                        verified -> {
                            assertThat(verified.id()).isEqualTo(player.id());
                            assertThat(verified.projectId()).isEqualTo(PROJECT);
                        });

        User user = administrator();
        String userToken = accessTokens.issue(user, NOW, NOW.plus(Duration.ofMinutes(15)));
        assertThat(accessTokens.verify(userToken)).isPresent();
    }

    @Test
    void an_expired_player_token_is_refused() {
        String token = playerTokens.issue(player(), NOW.minus(Duration.ofHours(2)), NOW.minus(Duration.ofHours(1)));

        assertThat(playerTokens.verify(token)).isEmpty();
    }

    @Test
    void a_player_token_signed_with_another_secret_is_refused() {
        JwtProperties other = properties();
        other.setSecret("a-different-secret-also-long-enough-for-hs256-signing");
        String foreign =
                new JwtPlayerTokens(other, clock).issue(player(), NOW, NOW.plus(Duration.ofHours(1)));

        assertThat(playerTokens.verify(foreign)).isEmpty();
    }

    @Test
    void nonsense_is_refused_rather_than_throwing() {
        assertThat(playerTokens.verify("not-a-token")).isEmpty();
        assertThat(playerTokens.verify("")).isEmpty();
    }
}
