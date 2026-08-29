// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.application.identity.port.out.ApiKeyRepository;
import io.ludus.application.identity.port.out.SecretDigester;
import io.ludus.application.identity.port.out.SecretGenerator;
import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.ApiKeyId;
import io.ludus.domain.identity.Role;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.util.List;
import java.util.Optional;

/**
 * Issuing, listing, revoking and checking API keys.
 *
 * <p>An API key is a password that gets written into a configuration file, committed by accident,
 * pasted into a chat and shipped inside a game binary that anyone can unpack. Every decision here
 * follows from assuming all of that will happen to at least one key.
 *
 * <p>So: it is shown exactly once and stored only as a digest, it is scoped to one project, it
 * cannot be more than a {@link Role#VIEWER} — a leaked key reads published content and can do
 * nothing else — and revoking it is a timestamp rather than a deletion, so the record of when it
 * stopped working survives the incident.
 */
public class ApiKeys {

    /**
     * Prefixes the visible part so a leaked key is recognisable as one. Secret scanners match on
     * patterns like this, which turns "someone committed a key" from a silent event into an alert.
     */
    public static final String KEY_PREFIX = "ludus_";

    private final ApiKeyRepository keys;
    private final SecretGenerator secrets;
    private final SecretDigester digester;
    private final Clock clock;

    public ApiKeys(
            ApiKeyRepository keys,
            SecretGenerator secrets,
            SecretDigester digester,
            Clock clock) {
        this.keys = keys;
        this.secrets = secrets;
        this.digester = digester;
        this.clock = clock;
    }

    /**
     * Mints a key. The returned plaintext exists nowhere else and cannot be recovered afterwards
     * by anyone, including whoever runs the database.
     */
    public NewApiKey issue(ProjectId projectId, String name) {
        String secret = KEY_PREFIX + secrets.generate();
        ApiKey key =
                ApiKey.create(
                        projectId,
                        name,
                        secret.substring(0, ApiKey.PREFIX_LENGTH),
                        digester.digest(secret),
                        Role.VIEWER,
                        clock.instant());
        return new NewApiKey(keys.save(key), secret);
    }

    /** Resolves a presented key, or empty if it is unknown or revoked. */
    public Optional<ApiKey> authenticate(ProjectId projectId, String presented) {
        if (presented == null || presented.isBlank()) {
            return Optional.empty();
        }
        return keys.findByDigest(projectId, digester.digest(presented))
                .filter(key -> !key.isRevoked());
    }

    public List<ApiKey> list(ProjectId projectId) {
        return keys.listIn(projectId);
    }

    /** @return the revoked key, or empty if there was no such key in this project */
    public Optional<ApiKey> revoke(ProjectId projectId, ApiKeyId id) {
        return keys.findById(projectId, id).map(key -> keys.save(key.revokedAt(clock.instant())));
    }

    /** A key and the one and only copy of its plaintext. */
    public record NewApiKey(ApiKey key, String plaintext) {}
}
