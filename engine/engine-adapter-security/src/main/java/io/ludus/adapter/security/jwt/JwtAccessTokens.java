// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.jwt;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.ludus.application.identity.port.out.AccessTokenIssuer;
import io.ludus.domain.identity.Role;
import io.ludus.domain.identity.User;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;
import java.util.UUID;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;

/**
 * Issues and verifies access tokens as HS256 JWTs.
 *
 * <p>Symmetric signing, because the only party that verifies these tokens is the same one that
 * issues them. Asymmetric keys buy the ability to let something else verify without being able to
 * mint, and nothing here needs that yet; adding it later changes this class and nothing else,
 * because the application only knows {@link AccessTokenIssuer}.
 *
 * <p>The project is a claim. It is what makes a token answer "which project" without a database
 * lookup, and it is checked against the active project on every request — a token minted for one
 * project is not usable against another even if the signature is perfectly valid.
 */
@Component
public class JwtAccessTokens implements AccessTokenIssuer {

    static final String CLAIM_PROJECT = "pid";
    static final String CLAIM_ROLE = "role";

    /**
     * Which kind of token this is, and why it is stamped rather than inferred.
     *
     * <p>Player session tokens are signed with the same secret, so without this the two differ only
     * in which claims they happen to carry. A player token presented here would today be rejected
     * because it has no {@code role} claim and {@code Role.fromString(null)} throws — which is
     * accidental safety, and stops being safe the first time somebody makes the role optional with
     * a sensible default. Stamped and required, the separation does not depend on that.
     *
     * <p>Introducing it invalidates tokens issued by an older build. They last fifteen minutes by
     * default, so a deploy resolves itself; it is a re-login at worst, not a migration.
     */
    static final String CLAIM_TYPE = "typ";

    static final String TYPE_USER = "user";

    private final SecretKey key;
    private final String issuer;
    private final java.time.Clock clock;

    public JwtAccessTokens(JwtProperties properties, java.time.Clock clock) {
        this.key =
                io.jsonwebtoken.security.Keys.hmacShaKeyFor(
                        properties.getSecret().getBytes(StandardCharsets.UTF_8));
        this.issuer = properties.getIssuer();
        this.clock = clock;
    }

    @Override
    public String issue(User user, Instant issuedAt, Instant expiresAt) {
        return Jwts.builder()
                .issuer(issuer)
                .subject(user.id().toString())
                .claim(CLAIM_PROJECT, user.projectId().toString())
                .claim(CLAIM_ROLE, user.role().name())
                .claim(CLAIM_TYPE, TYPE_USER)
                .issuedAt(Date.from(issuedAt))
                .expiration(Date.from(expiresAt))
                .signWith(key)
                .compact();
    }

    /**
     * Verifies a token and returns who it says the caller is.
     *
     * <p>Empty for every kind of invalid: bad signature, expired, wrong issuer, malformed, or
     * carrying claims that are not the shape this engine writes. The caller gets no detail,
     * because the difference between "expired" and "forged" is not something to tell whoever
     * presented it.
     */
    public Optional<VerifiedToken> verify(String token) {
        try {
            Claims claims =
                    Jwts.parser()
                            .verifyWith(key)
                            .requireIssuer(issuer)
                            // A player session token must not authenticate a person, whatever
                            // else it carries.
                            .require(CLAIM_TYPE, TYPE_USER)
                            // The same clock the tokens were issued against. Left to default,
                            // this reads the wall clock, and every assertion about expiry
                            // becomes a statement about when the test happened to run.
                            .clock(() -> Date.from(clock.instant()))
                            .build()
                            .parseSignedClaims(token)
                            .getPayload();

            return Optional.of(
                    new VerifiedToken(
                            new UserId(UUID.fromString(claims.getSubject())),
                            new ProjectId(UUID.fromString(claims.get(CLAIM_PROJECT, String.class))),
                            Role.fromString(claims.get(CLAIM_ROLE, String.class))));
        } catch (JwtException | IllegalArgumentException | NullPointerException invalid) {
            return Optional.empty();
        }
    }

    /** What a valid token asserts. */
    public record VerifiedToken(UserId userId, ProjectId projectId, Role role) {}
}
