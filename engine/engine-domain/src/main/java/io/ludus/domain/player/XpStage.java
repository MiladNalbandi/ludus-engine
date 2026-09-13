// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.player;

import java.util.List;

/**
 * One step of a project's XP curve: the total at which it begins.
 *
 * <p>Cumulative rather than per-stage, so "how far to the next one" is a subtraction instead of a
 * running sum over every earlier row — and so inserting a stage in the middle does not shift the
 * meaning of the ones after it.
 */
public record XpStage(int stage, long xpRequired, String label) {

    public XpStage {
        if (stage < 0) {
            throw new IllegalArgumentException("a stage must not be negative, was " + stage);
        }
        if (xpRequired < 0) {
            throw new IllegalArgumentException("a stage threshold must not be negative");
        }
    }

    /**
     * Which stage a total of XP reaches, given a project's curve.
     *
     * <p>The highest stage whose threshold has been met. Returns empty for a project with no curve
     * at all, which is the honest answer: a game that has not defined stages does not have a stage
     * to report, and inventing "stage 0" would have clients render a progress bar out of nothing.
     *
     * <p>Pure, and takes the curve as an argument rather than reading it, so the interesting cases
     * — an empty curve, a curve that does not start at zero, a gap — are testable without a
     * database.
     */
    public static java.util.Optional<XpStage> reached(List<XpStage> curve, long xp) {
        return curve.stream()
                .filter(candidate -> xp >= candidate.xpRequired())
                .max(java.util.Comparator.comparingLong(XpStage::xpRequired));
    }

    /** The next stage up, or empty at the top of the curve. */
    public static java.util.Optional<XpStage> next(List<XpStage> curve, long xp) {
        return curve.stream()
                .filter(candidate -> xp < candidate.xpRequired())
                .min(java.util.Comparator.comparingLong(XpStage::xpRequired));
    }
}
