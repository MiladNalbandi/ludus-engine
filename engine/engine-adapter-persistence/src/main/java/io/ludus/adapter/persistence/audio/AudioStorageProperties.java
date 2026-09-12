// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.audio;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Binds {@code ludus.audio.*} — {@code LUDUS_AUDIO_DIRECTORY} in a deployment.
 *
 * <p>A directory on disk rather than a column in the database. Audio is large, immutable once
 * uploaded, and streamed straight to a client; none of that benefits from being in Postgres, and
 * all of it makes backups larger and restores slower. The trade is that the directory has to be a
 * real volume, which the compose file provides and the deployment guide says out loud.
 */
@ConfigurationProperties(prefix = "ludus.audio")
public class AudioStorageProperties {

    /** Where clip bytes are written. Must survive a container restart. */
    private String directory = "";

    public String getDirectory() {
        return directory;
    }

    public void setDirectory(String directory) {
        this.directory = directory;
    }
}
