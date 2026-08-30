// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import java.util.Collection;
import java.util.Optional;

/**
 * Where a wave sits in the progression, and the rules about it.
 *
 * <p>Named after the behaviour rather than after the column, because the column is the part that
 * misleads. {@code wave_order} is <em>derived</em> from {@code progression_config.order} inside the
 * document and is never a request field. Anyone reading the entity will be tempted to expose it as
 * settable, at which point the document and the column can disagree and the document — the thing
 * clients actually receive — becomes the wrong one.
 *
 * <p>A collision is rejected rather than resolved. Silently shifting other waves to make room
 * changes content the author did not touch, and the author is the only one who knows which of the
 * two should come first.
 */
public final class WaveOrderPolicy {

    /** The JSON Pointer a collision is reported at, so an editor can highlight the field. */
    public static final String ORDER_POINTER = "/progression_config/order";

    private WaveOrderPolicy() {}

    /**
     * The order to suggest for a new wave: one past the highest taken, or zero when there are none.
     *
     * <p>Suggested, not assigned. The document carries the order and the author owns it; this only
     * answers "what would not collide right now", which is a question an editor asks before it
     * writes the document.
     */
    public static int suggestNext(Collection<Integer> taken) {
        if (taken == null || taken.isEmpty()) {
            return 0;
        }
        return taken.stream().mapToInt(Integer::intValue).max().orElse(-1) + 1;
    }

    /**
     * @param order the order the document asks for
     * @param takenBySomeoneElse the orders already held by <em>other</em> waves — an update that
     *     keeps its own order must not collide with itself
     * @return the offending order, if it is already taken
     */
    public static Optional<Integer> collision(int order, Collection<Integer> takenBySomeoneElse) {
        if (order < 0) {
            throw new IllegalArgumentException(
                    "order must not be negative, was " + order + " at " + ORDER_POINTER);
        }
        return takenBySomeoneElse != null && takenBySomeoneElse.contains(order)
                ? Optional.of(order)
                : Optional.empty();
    }
}
