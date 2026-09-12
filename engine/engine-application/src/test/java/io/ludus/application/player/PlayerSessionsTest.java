// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.application.player.port.out.PlayerTokenIssuer;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

/**
 * Starting sessions, and the idempotence that matters most.
 *
 * <p>A client retrying through a network blip must resolve the player it already has. Creating a
 * second one is not a duplicate row — it is a player whose progress has become unreachable, and the
 * person it happened to cannot be told why.
 */
class PlayerSessionsTest {

    private static final Instant NOW = Instant.parse("2026-09-12T13:00:00Z");
    private static final ProjectId MINE = ProjectId.random();
    private static final ProjectId THEIRS = ProjectId.random();

    private final Players players = new Players();
    private final Tokens tokens = new Tokens();
    private final PlayerSessions sessions =
            new PlayerSessions(players, tokens, Clock.fixed(NOW, ZoneOffset.UTC));

    @Test
    void a_first_session_creates_the_player() {
        PlayerSessions.Session session = sessions.start(MINE, "device-abc");

        assertThat(session.player().externalId()).isEqualTo("device-abc");
        assertThat(session.player().createdAt()).isEqualTo(NOW);
        assertThat(session.token()).isNotBlank();
        assertThat(session.expiresAt()).isEqualTo(NOW.plus(PlayerSessions.SESSION_LIFETIME));
    }

    @Test
    void starting_twice_resolves_the_same_player() {
        PlayerSessions.Session first = sessions.start(MINE, "device-abc");
        PlayerSessions.Session second = sessions.start(MINE, "device-abc");

        assertThat(second.player().id())
                .as("a retry must not make a second player whose predecessor's progress is lost")
                .isEqualTo(first.player().id());
        assertThat(players.saved).hasSize(1);
    }

    @Test
    void the_identifier_is_trimmed_so_whitespace_does_not_make_a_second_player() {
        PlayerSessions.Session first = sessions.start(MINE, "device-abc");
        PlayerSessions.Session second = sessions.start(MINE, "  device-abc  ");

        assertThat(second.player().id()).isEqualTo(first.player().id());
    }

    @Test
    void the_same_identifier_in_another_project_is_a_different_player() {
        PlayerSessions.Session mine = sessions.start(MINE, "device-abc");
        PlayerSessions.Session theirs = sessions.start(THEIRS, "device-abc");

        assertThat(theirs.player().id()).isNotEqualTo(mine.player().id());
        assertThat(theirs.player().projectId()).isEqualTo(THEIRS);
    }

    @Test
    void a_blank_identifier_is_refused() {
        assertThatThrownBy(() -> sessions.start(MINE, "  ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> sessions.start(MINE, null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void the_token_names_the_player_and_nobody_else() {
        PlayerSessions.Session session = sessions.start(MINE, "device-abc");

        assertThat(tokens.issuedFor).containsExactly(session.player().id());
    }

    @Test
    void a_player_from_another_project_is_not_found() {
        PlayerSessions.Session session = sessions.start(MINE, "device-abc");

        assertThat(sessions.find(THEIRS, session.player().id())).isEmpty();
        assertThat(sessions.find(MINE, session.player().id())).isPresent();
    }

    @Test
    void renaming_sets_and_clears_the_display_name() {
        PlayerSessions.Session session = sessions.start(MINE, "device-abc");

        assertThat(sessions.rename(MINE, session.player().id(), "  Alex  "))
                .get()
                .extracting(Player::displayName)
                .isEqualTo("Alex");

        assertThat(sessions.rename(MINE, session.player().id(), "   "))
                .as("a blank name clears it rather than storing an empty string")
                .get()
                .extracting(Player::displayName)
                .isNull();
    }

    @Test
    void renaming_a_player_in_another_project_does_nothing() {
        PlayerSessions.Session session = sessions.start(MINE, "device-abc");

        assertThat(sessions.rename(THEIRS, session.player().id(), "Hijacked")).isEmpty();
        assertThat(sessions.find(MINE, session.player().id()).orElseThrow().displayName()).isNull();
    }

    @Test
    void renaming_a_player_that_is_not_there_is_empty_rather_than_an_error() {
        assertThat(sessions.rename(MINE, PlayerId.random(), "Alex")).isEmpty();
    }

    // ------------------------------------------------------------------ fakes

    private static final class Players implements PlayerRepository {
        private final Map<PlayerId, Player> saved = new LinkedHashMap<>();

        @Override
        public Player save(Player player) {
            saved.put(player.id(), player);
            return player;
        }

        @Override
        public Optional<Player> find(ProjectId projectId, PlayerId id) {
            return Optional.ofNullable(saved.get(id)).filter(p -> p.projectId().equals(projectId));
        }

        @Override
        public Optional<Player> findByExternalId(ProjectId projectId, String externalId) {
            // The unique index is on (project_id, external_id); the fake must match it or a test
            // would pass here and fail against a real schema.
            return saved.values().stream()
                    .filter(p -> p.projectId().equals(projectId))
                    .filter(p -> p.externalId().equals(externalId))
                    .findFirst();
        }

        @Override
        public List<Player> page(ProjectId projectId, PlayerPageCursor after, int limit) {
            return saved.values().stream()
                    .filter(p -> p.projectId().equals(projectId))
                    .limit(limit)
                    .toList();
        }

        @Override
        public long count(ProjectId projectId) {
            return saved.values().stream().filter(p -> p.projectId().equals(projectId)).count();
        }

        @Override
        public boolean delete(ProjectId projectId, PlayerId id) {
            return find(projectId, id).isPresent() && saved.remove(id) != null;
        }
    }

    private static final class Tokens implements PlayerTokenIssuer {
        private final List<PlayerId> issuedFor = new ArrayList<>();

        @Override
        public String issue(Player player, Instant issuedAt, Instant expiresAt) {
            issuedFor.add(player.id());
            return "player-token-for-" + player.id();
        }
    }
}
