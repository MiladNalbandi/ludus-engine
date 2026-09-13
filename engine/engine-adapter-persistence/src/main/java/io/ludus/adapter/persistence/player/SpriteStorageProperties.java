// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Binds {@code ludus.sprite.*} — {@code LUDUS_SPRITE_DIRECTORY} in a deployment. */
@ConfigurationProperties(prefix = "ludus.sprite")
public class SpriteStorageProperties {

    /** Where sprite bytes are written. Must survive a container restart, like the audio one. */
    private String directory = "";

    public String getDirectory() {
        return directory;
    }

    public void setDirectory(String directory) {
        this.directory = directory;
    }
}
