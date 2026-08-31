// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.domain.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;

class ContentHashesTest {

    private static final Instant NOW = Instant.parse("2026-08-30T09:00:00Z");

    @Test
    void the_same_document_always_hashes_the_same() {
        ContentBody body = new ContentBody("{\"a\":1}");

        assertThat(ContentHashes.ofDocument(body))
                .isEqualTo(ContentHashes.ofDocument(new ContentBody("{\"a\":1}")))
                .startsWith(ContentHashes.PREFIX);
    }

    /** Whitespace is part of the bytes, and the bytes are what the ETag promises. */
    @Test
    void a_document_that_differs_only_in_whitespace_is_a_different_document() {
        assertThat(ContentHashes.ofDocument(new ContentBody("{\"a\":1}")))
                .isNotEqualTo(ContentHashes.ofDocument(new ContentBody("{ \"a\": 1 }")));
    }

    /**
     * The catalogue hash must not depend on what order the database returned rows in, or a client
     * would be told content changed every time the query planner changed its mind.
     */
    @Test
    void the_catalogue_hash_does_not_depend_on_row_order() {
        List<ContentHashes.Entry> one =
                List.of(
                        new ContentHashes.Entry("alpha", NOW),
                        new ContentHashes.Entry("beta", NOW.plusSeconds(60)));
        List<ContentHashes.Entry> reversed =
                List.of(
                        new ContentHashes.Entry("beta", NOW.plusSeconds(60)),
                        new ContentHashes.Entry("alpha", NOW));

        assertThat(ContentHashes.ofCatalogue(one)).isEqualTo(ContentHashes.ofCatalogue(reversed));
    }

    @Test
    void a_changed_timestamp_moves_the_catalogue_hash() {
        String before = ContentHashes.ofCatalogue(List.of(new ContentHashes.Entry("alpha", NOW)));
        String after =
                ContentHashes.ofCatalogue(
                        List.of(new ContentHashes.Entry("alpha", NOW.plusSeconds(1))));

        assertThat(after).isNotEqualTo(before);
    }

    @Test
    void adding_or_removing_content_moves_the_catalogue_hash() {
        String one = ContentHashes.ofCatalogue(List.of(new ContentHashes.Entry("alpha", NOW)));
        String two =
                ContentHashes.ofCatalogue(
                        List.of(
                                new ContentHashes.Entry("alpha", NOW),
                                new ContentHashes.Entry("beta", NOW)));

        assertThat(two).isNotEqualTo(one);
    }

    @Test
    void an_empty_catalogue_still_has_a_hash() {
        assertThat(ContentHashes.ofCatalogue(List.of())).startsWith(ContentHashes.PREFIX);
    }

    @Test
    void a_catalogue_entry_needs_both_of_its_parts() {
        assertThatIllegalArgumentException()
                .isThrownBy(() -> new ContentHashes.Entry(null, NOW));
        assertThatIllegalArgumentException()
                .isThrownBy(() -> new ContentHashes.Entry("alpha", null));
    }
}
