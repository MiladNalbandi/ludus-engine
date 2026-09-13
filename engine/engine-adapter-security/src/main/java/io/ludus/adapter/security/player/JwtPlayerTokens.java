// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.security.player;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.ludus.adapter.security.jwt.JwtProperties;
import io.ludus.application.player.port.out.PlayerTokenIssuer;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;
import java.util.UUID;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;

/**
 * Player session tokens, as HS256 JWTs.
 *
 * <p>Signed with the same secret as an administrative access token and <b>deliberately not
 * interchangeable with one</b>. The {@code typ} claim says which kind this is, and both verifiers
 * require their own value — so a player token presented on an admin route fails verification rather
 * than being read as a token with no role, and an access token presented as a player fails too.
 *
 * <p>That check is the whole reason the claim exists. Without it, two tokens signed by one key
 * differ only in which claims they happen to carry, and a verifier that tolerated a missing
 * {@code role} would quietly accept a player as an administrator. Sharing the secret is a
 * convenience; sharing an audience would be a vulnerability.
 */
@Component
public class JwtPlayerTokens implements PlayerTokenIssuer {

    static final String CLAIM_PROJECT = "pid";
    static final String CLAIM_TYPE = "typ";
    static final String TYPE_PLAYER = "player";

    private final SecretKey key;
    private final String issuer;
    private final Clock clock;

    public JwtPlayerTokens(JwtProperties properties, Clock clock) {
        this.key =
                io.jsonwebtoken.security.Keys.hmacShaKeyFor(
                        properties.getSecret().getBytes(StandardCharsets.UTF_8));
        this.issuer = properties.getIssuer();
        this.clock = clock;
    }

    @Override
    public String issue(Player player, Instant issuedAt, Instant expiresAt) {
        return Jwts.builder()
                .issuer(issuer)
                .subject(player.id().toString())
                .claim(CLAIM_PROJECT, player.projectId().toString())
                .claim(CLAIM_TYPE, TYPE_PLAYER)
                .issuedAt(Date.from(issuedAt))
                .expiration(Date.from(expiresAt))
                .signWith(key)
                .compact();
    }

    /**
     * The player a token names, or empty for every kind of invalid.
     *
     * <p>Bad signature, expired, wrong issuer, malformed, or — the case this method exists for —
     * the wrong kind of token entirely. The caller gets no detail, because "expired" and "forged"
     * are the same answer to whoever is asking.
     */
    public Optional<AuthenticatedPlayer> verify(String token) {
        try {
            Claims claims =
                    Jwts.parser()
                            .verifyWith(key)
                            .requireIssuer(issuer)
                            .require(CLAIM_TYPE, TYPE_PLAYER)
                            .clock(() -> Date.from(clock.instant()))
                            .build()
                            .parseSignedClaims(token)
                            .getPayload();

            return Optional.of(
                    new AuthenticatedPlayer(
                            new PlayerId(UUID.fromString(claims.getSubject())),
                            new ProjectId(UUID.fromString(claims.get(CLAIM_PROJECT, String.class)))));
        } catch (JwtException | IllegalArgumentException invalid) {
            return Optional.empty();
        }
    }

    /** Who a verified player token names. No role: a player has none, and cannot be given one. */
    public record AuthenticatedPlayer(PlayerId id, ProjectId projectId) {}
}
