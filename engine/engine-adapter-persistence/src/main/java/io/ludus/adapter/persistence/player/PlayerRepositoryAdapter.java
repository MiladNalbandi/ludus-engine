// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.application.player.port.out.PlayerRepository;
import io.ludus.domain.player.Player;
import io.ludus.domain.player.PlayerId;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Limit;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class PlayerRepositoryAdapter implements PlayerRepository {

    private final PlayerJpaRepository players;

    PlayerRepositoryAdapter(PlayerJpaRepository players) {
        this.players = players;
    }

    @Override
    @Transactional
    public Player save(Player player) {
        return players.save(PlayerEntity.from(player)).toDomain();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Player> find(ProjectId projectId, PlayerId id) {
        return players.findByIdAndProjectId(id.value(), projectId.value()).map(PlayerEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<Player> findByExternalId(ProjectId projectId, String externalId) {
        return players
                .findByProjectIdAndExternalId(projectId.value(), externalId)
                .map(PlayerEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public List<Player> page(ProjectId projectId, PlayerPageCursor after, int limit) {
        Limit page = Limit.of(limit);
        List<PlayerEntity> rows =
                after == null
                        ? players.findByProjectIdOrderByLastSeenAtDescIdDesc(projectId.value(), page)
                        : players.pageAfter(
                                projectId.value(), after.lastSeenAt(), after.id().value(), page);
        return rows.stream().map(PlayerEntity::toDomain).toList();
    }

    @Override
    @Transactional(readOnly = true)
    public long count(ProjectId projectId) {
        return players.countByProjectId(projectId.value());
    }

    @Override
    @Transactional
    public boolean delete(ProjectId projectId, PlayerId id) {
        return players.deleteByIdAndProjectId(id.value(), projectId.value()) > 0;
    }
}
