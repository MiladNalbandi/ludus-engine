// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.application.identity.port.out.SecretDigester;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;

/**
 * Exchanges a refresh token for a new pair of tokens.
 *
 * <p>The old refresh token is revoked as part of issuing the new one. That is rotation, and it
 * turns a stolen token from a permanent capability into a race: whichever party redeems it first
 * wins, and the other is left holding something that no longer works. It does not prevent theft,
 * but it puts a bound on how long theft is useful and gives the legitimate user a visible
 * symptom — being signed out — rather than a silent co-tenant.
 */
public class RefreshAccessToken {

    private final RefreshTokenRepository refreshTokens;
    private final UserRepository users;
    private final SecretDigester digester;
    private final AuthenticateUser issuing;
    private final Clock clock;

    public RefreshAccessToken(
            RefreshTokenRepository refreshTokens,
            UserRepository users,
            SecretDigester digester,
            AuthenticateUser issuing,
            Clock clock) {
        this.refreshTokens = refreshTokens;
        this.users = users;
        this.digester = digester;
        this.issuing = issuing;
        this.clock = clock;
    }

    public IssuedTokens refresh(ProjectId projectId, String presentedToken) {
        if (presentedToken == null || presentedToken.isBlank()) {
            throw new AuthenticationFailed("no refresh token supplied");
        }
        Instant now = clock.instant();

        RefreshToken stored =
                refreshTokens
                        .findByDigest(projectId, digester.digest(presentedToken))
                        .orElseThrow(() -> new AuthenticationFailed("no such refresh token"));

        if (!stored.isUsableAt(now)) {
            throw new AuthenticationFailed("refresh token is expired or revoked");
        }

        User user =
                users.findById(projectId, stored.userId())
                        .orElseThrow(
                                () -> new AuthenticationFailed(
                                        "refresh token belongs to a user that no longer exists"));

        if (!user.enabled()) {
            throw new AuthenticationFailed("account is disabled");
        }

        refreshTokens.save(stored.revokedAt(now));
        return issuing.issueFor(user);
    }
}
