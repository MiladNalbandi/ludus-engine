"""AC-3: what real clients and proxies actually send in If-None-Match.

Getting this wrong fails nothing. It silently turns caching off for one platform's HTTP stack,
and the only symptom is a bill. That is why it is a table rather than a couple of examples.
"""

import pytest

from wavemaker.apps.content.domain.etag import matches, quote


@pytest.mark.parametrize(
    ("header", "current", "expected"),
    [
        # the plain case, and the one every client sends after a 200
        ('"abc"', "abc", True),
        ('"abc"', "def", False),
        # a weak validator. Two representations that are equivalent but not byte-identical;
        # for a cache revalidation that is still a hit.
        ('W/"abc"', "abc", True),
        ('w/"abc"', "abc", True),
        # unquoted, which the specification does not allow and clients send anyway
        ("abc", "abc", True),
        # a list, which is what a client sends when it holds more than one version
        ('"old", "abc"', "abc", True),
        ('"old","abc"', "abc", True),
        ('W/"old", W/"abc"', "abc", True),
        ('"one", "two"', "abc", False),
        # "any representation you have" — a conditional GET that only wants to know it exists
        ("*", "abc", True),
        # nothing to compare against is not a match; it is a plain request
        ("", "abc", False),
        ("   ", "abc", False),
        # malformed input must be a miss, never an error and never a false hit
        ('"unterminated', "abc", False),
        ('""', "abc", False),
        ("W/", "abc", False),
    ],
)
def test_ac3_if_none_match_is_read_the_way_clients_write_it(
    header: str, current: str, expected: bool
) -> None:
    assert matches(header, current) is expected


def test_ac3_no_header_at_all_is_not_a_match() -> None:
    assert matches(None, "abc") is False


def test_ac3_a_tag_is_quoted_when_it_goes_out() -> None:
    assert quote("abc") == '"abc"'


def test_ac3_a_star_does_not_match_when_there_is_no_representation() -> None:
    """`*` means "any version you have". With nothing published there is no version."""
    assert matches("*", "") is False
