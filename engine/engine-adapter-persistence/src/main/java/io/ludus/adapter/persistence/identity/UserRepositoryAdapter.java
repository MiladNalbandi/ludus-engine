// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.identity;

import io.ludus.application.identity.port.out.UserRepository;
import io.ludus.domain.identity.EmailAddress;
import io.ludus.domain.identity.User;
import io.ludus.domain.identity.UserId;
import io.ludus.domain.project.ProjectId;
import java.util.Optional;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class UserRepositoryAdapter implements UserRepository {

    private final UserJpaRepository users;

    UserRepositoryAdapter(UserJpaRepository users) {
        this.users = users;
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<User> findByEmail(ProjectId projectId, EmailAddress email) {
        return users.findByProjectIdAndEmail(projectId.value(), email.value())
                .map(UserEntity::toDomain);
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<User> findById(ProjectId projectId, UserId id) {
        return users.findByProjectIdAndId(projectId.value(), id.value()).map(UserEntity::toDomain);
    }

    @Override
    @Transactional
    public User save(User user) {
        return users.save(UserEntity.from(user)).toDomain();
    }

    @Override
    @Transactional(readOnly = true)
    public long countIn(ProjectId projectId) {
        return users.countByProjectId(projectId.value());
    }
}
