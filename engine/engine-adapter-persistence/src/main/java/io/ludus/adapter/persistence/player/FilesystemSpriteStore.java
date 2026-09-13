// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.persistence.player;

import io.ludus.adapter.persistence.blob.FilesystemBlobs;
import io.ludus.application.player.port.out.SpriteStore;
import io.ludus.domain.player.SpriteId;
import jakarta.annotation.PostConstruct;
import java.io.InputStream;
import java.util.Optional;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.stereotype.Component;

/**
 * Sprite bytes on a filesystem.
 *
 * <p>All of the actual work is {@link FilesystemBlobs}, shared with audio — the atomic write, the
 * startup writability check and the refusal to let a client-supplied name reach a path were learned
 * once and are not worth learning twice.
 */
@Component
@EnableConfigurationProperties(SpriteStorageProperties.class)
public class FilesystemSpriteStore implements SpriteStore {

    private final FilesystemBlobs blobs;

    FilesystemSpriteStore(SpriteStorageProperties properties) {
        this.blobs =
                new FilesystemBlobs(properties.getDirectory(), "sprite", "LUDUS_SPRITE_DIRECTORY");
    }

    @PostConstruct
    void ensureWritable() {
        blobs.ensureWritable();
    }

    @Override
    public long store(SpriteId id, InputStream bytes) {
        return blobs.store(id.value(), bytes);
    }

    @Override
    public Optional<InputStream> open(SpriteId id) {
        return blobs.open(id.value());
    }

    @Override
    public boolean delete(SpriteId id) {
        return blobs.delete(id.value());
    }
}
