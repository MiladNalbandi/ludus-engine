// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatExceptionOfType;

import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class RefreshAccessTokenTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");
    private static final ProjectId PROJECT = ProjectId.random();
    private static final ProjectId OTHER_PROJECT = ProjectId.random();

    private final IdentityFakes.Users users = new IdentityFakes.Users();
    private final IdentityFakes.RefreshTokens refreshTokens = new IdentityFakes.RefreshTokens();
    private final IdentityFakes.Passwords passwords = new IdentityFakes.Passwords();
    private final IdentityFakes.Digester digester = new IdentityFakes.Digester();

    private final MutableClock clock = new MutableClock(NOW);

    private final AuthenticateUser authenticate =
            new AuthenticateUser(
                    users,
                    refreshTokens,
                    passwords,
                    new IdentityFakes.AccessTokens(),
                    new IdentityFakes.Secrets(),
                    digester,
                    TokenLifetimes.defaults(),
                    clock);

    private final RefreshAccessToken refresh =
            new RefreshAccessToken(refreshTokens, users, digester, authenticate, clock);

    private final User ada =
            users.save(
                    User.create(
                            PROJECT,
                            new EmailAddress("ada@example.com"),
                            passwords.hash("pw"),
                            Role.EDITOR,
                            NOW));

    @Test
    void a_valid_refresh_token_produces_a_new_pair() {
        IssuedTokens first = authenticate.authenticate(PROJECT, "ada@example.com", "pw");

        IssuedTokens second = refresh.refresh(PROJECT, first.refreshToken());

        assertThat(second.refreshToken()).isNotEqualTo(first.refreshToken());
        assertThat(second.accessToken()).isNotBlank();
    }

    /**
     * Rotation. Without it a stolen refresh token is a permanent capability; with it, redeeming
     * one invalidates it, so the thief and the owner cannot both keep working and the owner
     * notices by being signed out.
     */
    @Test
    void redeeming_a_refresh_token_stops_it_working_again() {
        IssuedTokens first = authenticate.authenticate(PROJECT, "ada@example.com", "pw");
        refresh.refresh(PROJECT, first.refreshToken());

        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(PROJECT, first.refreshToken()))
                .satisfies(
                        f ->
                                assertThat(f.reason())
                                        .isEqualTo("refresh token is expired or revoked"));
    }

    @Test
    void an_expired_refresh_token_is_refused() {
        IssuedTokens issued = authenticate.authenticate(PROJECT, "ada@example.com", "pw");

        clock.advanceBy(TokenLifetimes.defaults().refreshToken().plus(Duration.ofSeconds(1)));

        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(PROJECT, issued.refreshToken()))
                .satisfies(
                        f ->
                                assertThat(f.reason())
                                        .isEqualTo("refresh token is expired or revoked"));
    }

    @Test
    void a_refresh_token_cannot_be_redeemed_against_another_project() {
        IssuedTokens issued = authenticate.authenticate(PROJECT, "ada@example.com", "pw");

        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(OTHER_PROJECT, issued.refreshToken()))
                .satisfies(f -> assertThat(f.reason()).isEqualTo("no such refresh token"));
    }

    @Test
    void an_unknown_refresh_token_is_refused() {
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(PROJECT, "never-issued"))
                .satisfies(f -> assertThat(f.reason()).isEqualTo("no such refresh token"));
    }

    @Test
    void a_disabled_account_cannot_refresh_its_way_back_in() {
        IssuedTokens issued = authenticate.authenticate(PROJECT, "ada@example.com", "pw");
        users.save(ada.disabled());

        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(PROJECT, issued.refreshToken()))
                .satisfies(f -> assertThat(f.reason()).isEqualTo("account is disabled"));
    }

    @Test
    void signing_out_everywhere_revokes_every_live_token() {
        IssuedTokens laptop = authenticate.authenticate(PROJECT, "ada@example.com", "pw");
        IssuedTokens phone = authenticate.authenticate(PROJECT, "ada@example.com", "pw");

        int revoked = new SignOutEverywhere(refreshTokens, clock).signOut(PROJECT, ada.id());

        assertThat(revoked).isEqualTo(2);
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(PROJECT, laptop.refreshToken()));
        assertThatExceptionOfType(AuthenticationFailed.class)
                .isThrownBy(() -> refresh.refresh(PROJECT, phone.refreshToken()));
    }

    /** A clock a test can move, so expiry is exercised without the test taking thirty days. */
    private static final class MutableClock extends Clock {
        private Instant now;

        MutableClock(Instant start) {
            this.now = start;
        }

        void advanceBy(Duration amount) {
            now = now.plus(amount);
        }

        @Override
        public Instant instant() {
            return now;
        }

        @Override
        public java.time.ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(java.time.ZoneId zone) {
            return this;
        }
    }
}
