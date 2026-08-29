// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import io.ludus.application.identity.port.out.AccessTokenIssuer;
import io.ludus.application.identity.port.out.ApiKeyRepository;
import io.ludus.application.identity.port.out.PasswordHasher;
import io.ludus.application.identity.port.out.RefreshTokenRepository;
import io.ludus.application.identity.port.out.SecretDigester;
import io.ludus.application.identity.port.out.SecretGenerator;
import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.ApiKeyId;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.PasswordHash;
import io.ludus.domain.identity.RefreshToken;
import io.ludus.domain.identity.SecretDigest;
import io.ludus.domain.identity.User;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Hand-written stand-ins for the identity ports.
 *
 * <p>No mocking framework. These are short enough to read in one sitting, and unlike a mock they
 * actually behave — the repositories really filter by project, so a use case that forgets to pass
 * one fails here rather than passing against a stub that returns whatever it was told to.
 */
final class IdentityFakes {

    private IdentityFakes() {}

    static final class Users implements UserRepository {
        private final Map<UserId, User> byId = new LinkedHashMap<>();

        @Override
        public Optional<User> findByEmail(ProjectId projectId, EmailAddress email) {
            return byId.values().stream()
                    .filter(u -> u.projectId().equals(projectId) && u.email().equals(email))
                    .findFirst();
        }

        @Override
        public Optional<User> findById(ProjectId projectId, UserId id) {
            return Optional.ofNullable(byId.get(id)).filter(u -> u.projectId().equals(projectId));
        }

        @Override
        public User save(User user) {
            byId.put(user.id(), user);
            return user;
        }

        @Override
        public long countIn(ProjectId projectId) {
            return byId.values().stream().filter(u -> u.projectId().equals(projectId)).count();
        }
    }

    static final class RefreshTokens implements RefreshTokenRepository {
        final List<RefreshToken> all = new ArrayList<>();

        @Override
        public RefreshToken save(RefreshToken token) {
            all.removeIf(t -> t.id().equals(token.id()));
            all.add(token);
            return token;
        }

        @Override
        public Optional<RefreshToken> findByDigest(ProjectId projectId, SecretDigest digest) {
            return all.stream()
                    .filter(t -> t.projectId().equals(projectId) && t.tokenDigest().equals(digest))
                    .findFirst();
        }

        @Override
        public int revokeAllFor(ProjectId projectId, UserId userId, Instant when) {
            List<RefreshToken> live =
                    all.stream()
                            .filter(
                                    t ->
                                            t.projectId().equals(projectId)
                                                    && t.userId().equals(userId)
                                                    && t.revokedAt() == null)
                            .toList();
            live.forEach(t -> save(t.revokedAt(when)));
            return live.size();
        }
    }

    static final class Keys implements ApiKeyRepository {
        private final Map<ApiKeyId, ApiKey> byId = new LinkedHashMap<>();

        @Override
        public ApiKey save(ApiKey key) {
            byId.put(key.id(), key);
            return key;
        }

        @Override
        public Optional<ApiKey> findByDigest(ProjectId projectId, SecretDigest digest) {
            return byId.values().stream()
                    .filter(k -> k.projectId().equals(projectId) && k.secretDigest().equals(digest))
                    .findFirst();
        }

        @Override
        public Optional<ApiKey> findById(ProjectId projectId, ApiKeyId id) {
            return Optional.ofNullable(byId.get(id)).filter(k -> k.projectId().equals(projectId));
        }

        @Override
        public List<ApiKey> listIn(ProjectId projectId) {
            return byId.values().stream().filter(k -> k.projectId().equals(projectId)).toList();
        }
    }

    /**
     * Reversible "hashing". Obviously wrong for production and exactly right here: the use case
     * tests are about which branch is taken, not about BCrypt, and a real hash would make them
     * slow for no added confidence. The real implementation has its own test.
     */
    static final class Passwords implements PasswordHasher {
        final AtomicInteger decoyChecks = new AtomicInteger();

        @Override
        public PasswordHash hash(String rawPassword) {
            return new PasswordHash("hashed:" + rawPassword);
        }

        @Override
        public boolean matches(String rawPassword, PasswordHash hash) {
            return hash.value().equals("hashed:" + rawPassword);
        }

        @Override
        public boolean matchesNothing(String rawPassword) {
            decoyChecks.incrementAndGet();
            return false;
        }
    }

    /**
     * Deterministic, and deliberately does not contain its input.
     *
     * <p>The first version of this returned {@code "digest:" + secret}, which is deterministic
     * and was enough to make the lookups work — and the test asserting that a stored credential
     * does not contain its own plaintext failed against it, correctly. A fake that leaks what the
     * real one hides will pass every test except the one that matters.
     */
    static final class Digester implements SecretDigester {
        @Override
        public SecretDigest digest(String secret) {
            return new SecretDigest(
                    "d" + Integer.toHexString(secret.hashCode()) + "l" + secret.length());
        }
    }

    /** Counts up, so a test can name the exact token it expects to have been issued. */
    static final class Secrets implements SecretGenerator {
        private final AtomicInteger next = new AtomicInteger();

        @Override
        public String generate() {
            return "secret-" + next.incrementAndGet();
        }
    }

    static final class AccessTokens implements AccessTokenIssuer {
        @Override
        public String issue(User user, Instant issuedAt, Instant expiresAt) {
            return "access[" + user.id() + "@" + user.projectId() + "|" + expiresAt + "]";
        }
    }
}
