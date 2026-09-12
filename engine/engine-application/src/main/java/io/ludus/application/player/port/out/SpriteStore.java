// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.player.port.out;

import io.ludus.domain.player.SpriteId;
import java.io.InputStream;
import java.util.Optional;

/**
 * Where sprite bytes live.
 *
 * <p>Streams both ways, like {@code AudioStore} and for the same reason: an image is small enough
 * that a byte array looks harmless, and an endpoint serving fifty of them to a client that has just
 * installed the game is fifty copies in the heap at once.
 *
 * <p>Bytes are addressed by id alone. The uploaded filename never reaches this interface.
 */
public interface SpriteStore {

    long store(SpriteId id, InputStream bytes);

    Optional<InputStream> open(SpriteId id);

    boolean delete(SpriteId id);
}
