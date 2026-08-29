// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.identity;

import static org.assertj.core.api.Assertions.assertThat;

import io.ludus.domain.identity.ApiKey;
import io.ludus.domain.identity.ApiKeyId;
import io.ludus.domain.identity.Role;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class ApiKeysTest {

    private static final Instant NOW = Instant.parse("2026-08-28T09:00:00Z");
    private static final ProjectId PROJECT = ProjectId.random();
    private static final ProjectId OTHER_PROJECT = ProjectId.random();

    private final IdentityFakes.Keys stored = new IdentityFakes.Keys();
    private final IdentityFakes.Digester digester = new IdentityFakes.Digester();
    private final ApiKeys apiKeys =
            new ApiKeys(
                    stored,
                    new IdentityFakes.Secrets(),
                    digester,
                    Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void a_new_key_is_recognisable_and_authenticates() {
        ApiKeys.NewApiKey issued = apiKeys.issue(PROJECT, "android-client");

        assertThat(issued.plaintext()).startsWith(ApiKeys.KEY_PREFIX);
        assertThat(apiKeys.authenticate(PROJECT, issued.plaintext()))
                .map(ApiKey::name)
                .contains("android-client");
    }

    @Test
    void the_plaintext_is_never_stored() {
        ApiKeys.NewApiKey issued = apiKeys.issue(PROJECT, "android-client");

        assertThat(issued.key().secretDigest().value()).doesNotContain(issued.plaintext());
        assertThat(stored.listIn(PROJECT).get(0).secretDigest().value())
                .isEqualTo(digester.digest(issued.plaintext()).value());
    }

    /** The prefix is for a person reading a list, not for looking a key up. */
    @Test
    void the_prefix_is_the_visible_head_of_the_key_and_is_not_secret() {
        ApiKeys.NewApiKey issued = apiKeys.issue(PROJECT, "android-client");

        assertThat(issued.key().prefix())
                .hasSize(ApiKey.PREFIX_LENGTH)
                .isEqualTo(issued.plaintext().substring(0, ApiKey.PREFIX_LENGTH));
    }

    /**
     * A key ends up in a config file, a repository, and a shipped game binary. Anything it can do,
     * assume everyone can do, which is why it cannot be more than a viewer.
     */
    @Test
    void a_key_can_only_ever_read() {
        assertThat(apiKeys.issue(PROJECT, "android-client").key().role()).isEqualTo(Role.VIEWER);
    }

    @Test
    void a_revoked_key_stops_authenticating_but_stays_on_the_record() {
        ApiKeys.NewApiKey issued = apiKeys.issue(PROJECT, "android-client");

        apiKeys.revoke(PROJECT, issued.key().id());

        assertThat(apiKeys.authenticate(PROJECT, issued.plaintext())).isEmpty();
        assertThat(apiKeys.list(PROJECT)).singleElement().satisfies(
                key -> {
                    assertThat(key.isRevoked()).isTrue();
                    assertThat(key.revokedAt()).isEqualTo(NOW);
                });
    }

    @Test
    void a_key_does_not_authenticate_against_another_project() {
        ApiKeys.NewApiKey issued = apiKeys.issue(PROJECT, "android-client");

        assertThat(apiKeys.authenticate(OTHER_PROJECT, issued.plaintext())).isEmpty();
    }

    /** 404, not 403: from outside, "not yours" and "not there" must be indistinguishable. */
    @Test
    void revoking_another_projects_key_finds_nothing() {
        ApiKeys.NewApiKey issued = apiKeys.issue(PROJECT, "android-client");

        assertThat(apiKeys.revoke(OTHER_PROJECT, issued.key().id())).isEmpty();
        assertThat(apiKeys.authenticate(PROJECT, issued.plaintext()))
                .as("and it must not have been revoked as a side effect")
                .isPresent();
    }

    @Test
    void an_unknown_or_empty_key_authenticates_as_nobody() {
        assertThat(apiKeys.authenticate(PROJECT, "ludus_nonsense")).isEmpty();
        assertThat(apiKeys.authenticate(PROJECT, "")).isEmpty();
        assertThat(apiKeys.authenticate(PROJECT, null)).isEmpty();
        assertThat(apiKeys.revoke(PROJECT, ApiKeyId.random())).isEmpty();
    }
}
