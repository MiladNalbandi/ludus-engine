// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;

class WaveOrderPolicyTest {

    @Test
    void the_first_wave_is_suggested_order_zero() {
        assertThat(WaveOrderPolicy.suggestNext(List.of())).isZero();
        assertThat(WaveOrderPolicy.suggestNext(null)).isZero();
    }

    /** One past the highest, not "count", so a gap left by a deletion is not handed out twice. */
    @Test
    void the_suggestion_is_one_past_the_highest_taken() {
        assertThat(WaveOrderPolicy.suggestNext(List.of(0, 1, 5))).isEqualTo(6);
        assertThat(WaveOrderPolicy.suggestNext(Set.of(3))).isEqualTo(4);
    }

    @Test
    void a_taken_order_is_a_collision() {
        assertThat(WaveOrderPolicy.collision(2, List.of(0, 1, 2))).contains(2);
    }

    @Test
    void a_free_order_is_not() {
        assertThat(WaveOrderPolicy.collision(3, List.of(0, 1, 2))).isEmpty();
        assertThat(WaveOrderPolicy.collision(0, List.of())).isEmpty();
        assertThat(WaveOrderPolicy.collision(0, null)).isEmpty();
    }

    @Test
    void a_negative_order_is_refused_rather_than_reported_as_a_collision() {
        assertThatIllegalArgumentException()
                .isThrownBy(() -> WaveOrderPolicy.collision(-1, List.of()))
                .withMessageContaining(WaveOrderPolicy.ORDER_POINTER);
    }

    /** The pointer is part of the contract: an editor uses it to highlight the field. */
    @Test
    void the_order_pointer_is_a_json_pointer() {
        assertThat(WaveOrderPolicy.ORDER_POINTER).isEqualTo("/progression_config/order");
    }
}
