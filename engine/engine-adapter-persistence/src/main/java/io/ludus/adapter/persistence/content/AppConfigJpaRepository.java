// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.content;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

interface AppConfigJpaRepository extends JpaRepository<AppConfigEntity, UUID> {}
