// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * A table, because the whole value of this class is the breadth of what it accepts.
 *
 * <p>Every row here is something a real HTTP stack or proxy sends. A parser that handles only the
 * canonical quoted form works perfectly in a test written against itself and then silently disables
 * caching for whichever platform does something slightly different.
 */
class EntityTagsTest {

    private static final String TAG = "sha256:abc123";

    @ParameterizedTest(name = "[{index}] {0} matches")
    @ValueSource(
            strings = {
                "\"sha256:abc123\"", // the canonical form
                "sha256:abc123", // unquoted, which plenty of clients send
                "W/\"sha256:abc123\"", // weak, added by caches on their own
                "w/\"sha256:abc123\"", // lowercase marker, seen in the wild
                "  \"sha256:abc123\"  ", // surrounding whitespace
                "\"sha256:other\", \"sha256:abc123\"", // a list, second entry matches
                "\"sha256:abc123\",\"sha256:other\"", // a list with no space after the comma
                "W/\"sha256:other\", W/\"sha256:abc123\"", // a list of weak validators
                "*" // any representation
            })
    void these_all_mean_the_client_already_has_it(String header) {
        assertThat(EntityTags.matches(header, TAG)).isTrue();
    }

    @ParameterizedTest(name = "[{index}] {0} does not match")
    @ValueSource(
            strings = {
                "\"sha256:different\"",
                "sha256:abc12", // a prefix is not a match
                "sha256:abc1234", // nor is an extension
                "\"\"", // empty quoted
                "\",\"", // nothing but a separator
                "W/", // a marker and nothing else
                "\"sha256:x\", \"sha256:y\""
            })
    void these_do_not(String header) {
        assertThat(EntityTags.matches(header, TAG)).isFalse();
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {"   "})
    void an_absent_header_never_matches(String header) {
        assertThat(EntityTags.matches(header, TAG)).isFalse();
    }

    /**
     * Weak comparison on purpose. Strong comparison exists for byte-range requests and nothing here
     * serves ranges; treating {@code W/"x"} as different from {@code "x"} would mean refusing to
     * honour a cache entry that is in fact current.
     */
    @Test
    void a_weak_validator_matches_a_strong_tag() {
        assertThat(EntityTags.matches("W/\"" + TAG + "\"", TAG)).isTrue();
    }

    @Test
    void there_is_nothing_to_match_against_without_a_current_tag() {
        assertThat(EntityTags.matches("*", null)).isFalse();
        assertThat(EntityTags.matches("*", "")).isFalse();
        assertThat(EntityTags.matches("*", "  ")).isFalse();
    }

    /** Tolerant on the way in, canonical on the way out. */
    @Test
    void the_response_header_is_always_quoted() {
        assertThat(EntityTags.toHeader(TAG)).isEqualTo("\"sha256:abc123\"");
        assertThatIllegalArgumentException().isThrownBy(() -> EntityTags.toHeader(""));
        assertThatIllegalArgumentException().isThrownBy(() -> EntityTags.toHeader(null));
    }

    @ParameterizedTest(name = "round trip: {0}")
    @CsvSource({"sha256:abc123", "sha256:0000", "a"})
    void what_it_sends_is_something_it_would_accept_back(String tag) {
        assertThat(EntityTags.matches(EntityTags.toHeader(tag), tag)).isTrue();
    }
}
