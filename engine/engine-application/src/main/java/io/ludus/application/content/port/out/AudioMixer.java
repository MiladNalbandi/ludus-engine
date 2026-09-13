// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.application.content.port.out;

import io.ludus.domain.content.AudioClipId;
import java.io.InputStream;
import java.util.List;

/**
 * Combining several clips into one.
 *
 * <p>An outbound port because mixing needs a media tool the engine does not contain, and because
 * the implementation that uses one is the single most dangerous thing in this codebase. The
 * predecessor built an FFmpeg command as a string and handed it to {@code child_process.exec} —
 * through a shell, with interpolated filenames. Any authenticated editor user had shell execution
 * on the container. That is not a bug to be careful about; it is a design that has to be
 * impossible, so the port takes streams and ids and no paths at all, and nothing on this side of
 * it can describe a command.
 *
 * <p>It also lives here rather than in the editor, which the roadmap asks for explicitly: mixing in
 * the editor makes the editor stateful, and a stateful editor cannot run as more than one replica.
 */
public interface AudioMixer {

    /**
     * Whether this install can mix at all.
     *
     * <p>Most cannot, and that is the intended default. FFmpeg is a large dependency with its own
     * vulnerability history, and a self-hosted install should not have to acquire it to get a
     * working engine. Asked before a request is accepted, so the answer is a clear refusal rather
     * than a failure part-way through a job.
     */
    boolean available();

    /** A clip to include, and how loud. */
    record Source(AudioClipId id, InputStream bytes, double gainDb) {}

    /**
     * Mixes the sources into one clip.
     *
     * <p>The caller closes the returned stream, and closing it is what releases whatever the
     * implementation was holding — a temporary directory, usually. A caller that forgets leaks
     * disk rather than memory, which is why {@link #available()} exists to keep the number of
     * these in flight small.
     *
     * @throws MixFailed when the tool refused the input, took too long, or produced too much
     */
    Mixed mix(List<Source> sources);

    /** The mixed bytes, and what they are. */
    record Mixed(InputStream bytes, String contentType) {}

    /** Mixing did not produce a usable result. The message is shown to the editor. */
    class MixFailed extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public MixFailed(String message) {
            super(message);
        }

        public MixFailed(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
