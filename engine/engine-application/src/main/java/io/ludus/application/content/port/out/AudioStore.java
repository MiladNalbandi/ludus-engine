// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.AudioClipId;
import java.io.InputStream;
import java.util.Optional;

/**
 * Where audio bytes live.
 *
 * <p>Streams in both directions, and that is the whole interface design. The obvious signatures —
 * {@code byte[] read(id)} and {@code store(id, byte[])} — make a clip cost its own size in heap for
 * every request holding it. Whether that is fatal depends on the clip and the traffic, which is
 * exactly what makes it a bad way to find out: it is fine on a developer's machine with one 4 MB
 * effect and not fine on the day someone uploads the soundtrack. The codebase this was extracted
 * from ran into it with a 256 MB heap.
 *
 * <p>So the guard does not rely on load at all. {@code AudioStreamingIT} sends a clip larger than
 * the whole heap through both directions, where an array-shaped implementation cannot be allocated
 * under any conditions.
 *
 * <p>Bytes are addressed by id alone. The uploaded filename never reaches this interface, so no
 * implementation can be talked into opening a path a client chose.
 */
public interface AudioStore {

    /**
     * Consumes the stream and stores it. The caller closes the stream; this must not buffer it
     * whole in memory.
     *
     * @return how many bytes were actually stored, which the caller records as the clip's size
     *     rather than trusting a client-supplied length
     */
    long store(AudioClipId id, InputStream bytes);

    /**
     * Opens the stored bytes for reading. The caller closes the stream.
     *
     * <p>Empty when nothing is stored under that id — which, because metadata and bytes are stored
     * separately, is a real possibility worth handling rather than asserting away.
     */
    Optional<InputStream> open(AudioClipId id);

    /** @return true if there were bytes to remove */
    boolean delete(AudioClipId id);
}
