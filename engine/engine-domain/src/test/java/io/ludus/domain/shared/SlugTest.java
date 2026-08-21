// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.shared;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class SlugTest {

    @ParameterizedTest
    @ValueSource(strings = {"a", "wave_001", "boss_fight_2", "0"})
    void accepts_lowercase_alphanumeric_and_underscore(String value) {
        assertThat(new Slug(value).value()).isEqualTo(value);
    }

    @ParameterizedTest
    @ValueSource(strings = {"Wave_001", "wave-001", "wave 001", "wave.001", "wave/001", "wavé"})
    void rejects_anything_that_would_need_escaping_in_a_url_or_filename(String value) {
        assertThatThrownBy(() -> new Slug(value)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejects_blank_and_null() {
        assertThatThrownBy(() -> new Slug("")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Slug("   ")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new Slug(null)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejects_values_longer_than_the_column_it_is_stored_in() {
        String tooLong = "a".repeat(Slug.MAX_LENGTH + 1);
        assertThatThrownBy(() -> new Slug(tooLong))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("at most");
        assertThat(new Slug("a".repeat(Slug.MAX_LENGTH))).isNotNull();
    }

    @Test
    void isValid_agrees_with_the_constructor() {
        assertThat(Slug.isValid("wave_001")).isTrue();
        assertThat(Slug.isValid("Wave")).isFalse();
        assertThat(Slug.isValid(null)).isFalse();
    }
}
