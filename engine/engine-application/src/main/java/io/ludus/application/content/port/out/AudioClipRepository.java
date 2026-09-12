// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.AudioClip;
import io.ludus.domain.content.AudioClipId;
import io.ludus.domain.project.ProjectId;
import java.util.List;
import java.util.Optional;

/** Storage for what is known about audio clips, which is never their bytes. */
public interface AudioClipRepository {

    AudioClip save(AudioClip clip);

    Optional<AudioClip> find(ProjectId projectId, AudioClipId id);

    List<AudioClip> list(ProjectId projectId);

    boolean delete(ProjectId projectId, AudioClipId id);
}
