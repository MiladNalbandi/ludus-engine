// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.Sprite;
import io.ludus.domain.player.SpriteId;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;

/** Storage for what is known about sprites, which is never their bytes. */
public interface SpriteRepository {

    Sprite save(Sprite sprite);

    Optional<Sprite> find(ProjectId projectId, SpriteId id);

    List<Sprite> list(ProjectId projectId);

    boolean delete(ProjectId projectId, SpriteId id);
}
