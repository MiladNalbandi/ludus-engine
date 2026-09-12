// SPDX-License-Identifier: AGPL-3.0-or-later
package io.ludus.adapter.web.content;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import io.ludus.application.content.ContentRejected;
import io.ludus.domain.content.ContentBody;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

/**
 * The splitter, one row per thing that could break it.
 *
 * <p>Worth this much attention because the failure mode is silent. A splitter that mishandled a
 * brace inside a string would hand a truncated document to a validator, which would reject it with
 * a schema error naming a field — and the author would go looking at a document that is perfectly
 * fine. Nothing would point at the splitter.
 *
 * <p>Every assertion here is about <em>bytes</em>. The whole reason this class exists rather than a
 * {@code List<JsonNode>} parameter is that a parse-and-re-serialise round trip changes them, so a
 * test that compared parsed equality would pass on exactly the implementation being avoided.
 */
class JsonArraysTest {

    private static List<String> split(String array) {
        return JsonArrays.split(array).stream().map(ContentBody::json).toList();
    }

    @Test
    void two_plain_documents() {
        assertThat(split("[{\"id\":\"a\"},{\"id\":\"b\"}]"))
                .containsExactly("{\"id\":\"a\"}", "{\"id\":\"b\"}");
    }

    @Test
    void one_document() {
        assertThat(split("[{\"id\":\"a\"}]")).containsExactly("{\"id\":\"a\"}");
    }

    @Test
    void the_bytes_of_each_document_are_untouched() {
        String awkward = "{\"a\":1.0,   \"z\":true,\n  \"b\":[1,2,3]}";

        assertThat(split("[" + awkward + "]"))
                .as("whitespace, key order and 1.0 all survive; that is the point of the class")
                .containsExactly(awkward);
    }

    @Test
    void a_comma_inside_a_string_does_not_split_a_document() {
        assertThat(split("[{\"name\":\"a,b\"},{\"name\":\"c\"}]"))
                .containsExactly("{\"name\":\"a,b\"}", "{\"name\":\"c\"}");
    }

    @Test
    void a_brace_inside_a_string_does_not_change_the_depth() {
        assertThat(split("[{\"name\":\"}{\"},{\"name\":\"c\"}]"))
                .as("the classic way a hand-written scanner goes wrong")
                .containsExactly("{\"name\":\"}{\"}", "{\"name\":\"c\"}");
    }

    @Test
    void an_escaped_quote_does_not_end_a_string() {
        assertThat(split("[{\"name\":\"say \\\"hi\\\", then\"},{\"name\":\"c\"}]"))
                .containsExactly("{\"name\":\"say \\\"hi\\\", then\"}", "{\"name\":\"c\"}");
    }

    @Test
    void an_escaped_backslash_does_not_escape_the_quote_after_it() {
        // "path\\" -- the backslash is escaped, so the quote that follows really does close the
        // string. A scanner that treated the second backslash as an escape would run on and
        // swallow the rest of the array.
        assertThat(split("[{\"path\":\"c:\\\\\"},{\"id\":\"b\"}]"))
                .containsExactly("{\"path\":\"c:\\\\\"}", "{\"id\":\"b\"}");
    }

    @Test
    void nested_objects_and_arrays_are_one_document_each() {
        assertThat(split("[{\"a\":{\"b\":[{\"c\":1}]}},{\"d\":2}]"))
                .containsExactly("{\"a\":{\"b\":[{\"c\":1}]}}", "{\"d\":2}");
    }

    @Test
    void nested_arrays_containing_commas_do_not_split() {
        assertThat(split("[{\"waves\":[1,2,3]},{\"waves\":[4,5]}]"))
                .containsExactly("{\"waves\":[1,2,3]}", "{\"waves\":[4,5]}");
    }

    @Test
    void whitespace_and_newlines_around_elements_are_trimmed_but_not_inside_them() {
        assertThat(split("[\n  {\"id\":\"a\", \"n\":1},\n  {\"id\":\"b\"}\n]"))
                .containsExactly("{\"id\":\"a\", \"n\":1}", "{\"id\":\"b\"}");
    }

    @Test
    void a_bare_scalar_is_returned_as_an_element_so_the_violation_can_name_it() {
        // Not a document, and not this class's job to say so -- but it must come back as element 0
        // rather than as a complaint about the whole request, or the author cannot tell which entry
        // was wrong.
        assertThat(split("[42,{\"id\":\"b\"}]")).containsExactly("42", "{\"id\":\"b\"}");
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "   ", "{\"id\":\"a\"}", "[", "]", "not json at all"})
    void anything_that_is_not_an_array_is_refused(String body) {
        assertThatThrownBy(() -> split(body)).isInstanceOf(ContentRejected.class);
    }

    @Test
    void a_null_body_is_refused() {
        assertThatThrownBy(() -> split(null)).isInstanceOf(ContentRejected.class);
    }

    @Test
    void an_empty_array_is_refused_rather_than_importing_nothing_successfully() {
        assertThatThrownBy(() -> split("[]"))
                .as("a 201 for an import that imported nothing is a lie")
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void an_unclosed_document_is_refused_rather_than_truncated() {
        assertThatThrownBy(() -> split("[{\"id\":\"a\"]"))
                .isInstanceOf(ContentRejected.class);
    }

    @Test
    void an_unterminated_string_is_refused() {
        assertThatThrownBy(() -> split("[{\"id\":\"a}]")).isInstanceOf(ContentRejected.class);
    }

    @Test
    void a_trailing_comma_is_refused_rather_than_yielding_an_empty_element() {
        assertThatThrownBy(() -> split("[{\"id\":\"a\"},]"))
                .isInstanceOf(ContentRejected.class);
    }
}
