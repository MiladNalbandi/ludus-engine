// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.application.identity.port.out.AccessTokenIssuer;
import io.ludus.application.identity.port.out.PasswordHasher;
import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.application.identity.port.out.SecretDigester;
import io.ludus.application.identity.port.out.SecretGenerator;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.User;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

/** Exchanges an email address and a password for a pair of tokens. */
public class AuthenticateUser {

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final PasswordHasher passwords;
    private final AccessTokenIssuer accessTokens;
    private final SecretGenerator secrets;
    private final SecretDigester digester;
    private final TokenLifetimes lifetimes;
    private final Clock clock;

    public AuthenticateUser(
            UserRepository users,
            RefreshTokenRepository refreshTokens,
            PasswordHasher passwords,
            AccessTokenIssuer accessTokens,
            SecretGenerator secrets,
            SecretDigester digester,
            TokenLifetimes lifetimes,
            Clock clock) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.passwords = passwords;
        this.accessTokens = accessTokens;
        this.secrets = secrets;
        this.digester = digester;
        this.lifetimes = lifetimes;
        this.clock = clock;
    }

    public IssuedTokens authenticate(ProjectId projectId, String email, String rawPassword) {
        EmailAddress address = parse(email, rawPassword);
        Optional<User> found = users.findByEmail(projectId, address);

        if (found.isEmpty()) {
            // Burn the time a real check would take before failing. Returning immediately here
            // makes "no such account" measurably faster than "wrong password", which is enough
            // to enumerate who has an account without ever authenticating.
            passwords.matchesNothing(rawPassword);
            throw new AuthenticationFailed("no user with that address in this project");
        }

        User user = found.get();
        if (!passwords.matches(rawPassword, user.passwordHash())) {
            throw new AuthenticationFailed("password did not match");
        }
        if (!user.enabled()) {
            // Checked after the password on purpose: answering before it is verified tells an
            // attacker which addresses exist, in exchange for nothing.
            throw new AuthenticationFailed("account is disabled");
        }

        return issueFor(user);
    }

    /** Shared with {@link RefreshAccessToken}, which has already established who the user is. */
    IssuedTokens issueFor(User user) {
        Instant now = clock.instant();
        Instant accessExpiry = now.plus(lifetimes.accessToken());
        Instant refreshExpiry = now.plus(lifetimes.refreshToken());

        String refreshValue = secrets.generate();
        refreshTokens.save(
                RefreshToken.issue(
                        user.projectId(),
                        user.id(),
                        digester.digest(refreshValue),
                        now,
                        refreshExpiry));

        return new IssuedTokens(
                accessTokens.issue(user, now, accessExpiry),
                accessExpiry,
                refreshValue,
                refreshExpiry);
    }

    private EmailAddress parse(String email, String rawPassword) {
        if (rawPassword == null || rawPassword.isEmpty()) {
            throw new AuthenticationFailed("no password supplied");
        }
        try {
            return new EmailAddress(email);
        } catch (IllegalArgumentException malformed) {
            // A malformed address cannot match anything, but failing differently from a
            // well-formed one that does not exist would be another way to probe.
            passwords.matchesNothing(rawPassword);
            throw new AuthenticationFailed("malformed email address: " + malformed.getMessage());
        }
    }
}
