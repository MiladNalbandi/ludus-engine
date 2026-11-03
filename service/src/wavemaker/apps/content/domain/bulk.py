"""Splitting a JSON array back into the exact bytes of each document it holds.

An import arrives as `[{…},{…},{…}]` — the documents joined with commas, untouched. Each one
has to be stored exactly as it was written, so the array cannot simply be parsed: parsing and
re-serialising the elements rewrites `2.0` as `2`, reorders keys, and moves the ETag of every
wave in the batch.

So the array is walked instead, and each element's byte range is sliced out of the original.
`raw_decode` does the hard part: it parses one value and reports where that value ended.
"""

from __future__ import annotations

import json

from wavemaker.platform.kernel.errors import PlatformError

DECODER = json.JSONDecoder()


class BulkError(PlatformError):
    """The batch itself is malformed, before any single document is looked at."""


def split_documents(raw: bytes) -> list[bytes]:
    """The verbatim bytes of each element of a top-level JSON array.

    Whitespace between elements is formatting and is dropped; whitespace *inside* an element
    is part of that document and is kept.
    """
    try:
        text = raw.decode()
    except UnicodeDecodeError as broken:
        raise BulkError(f"This batch is not UTF-8: {broken}") from broken

    at = _skip_space(text, 0)
    if at >= len(text) or text[at] != "[":
        raise BulkError("A bulk import must be a JSON array of wave documents.")

    at = _skip_space(text, at + 1)
    if at < len(text) and text[at] == "]":
        # An empty batch is still a whole batch: `[] []` is two values, not an empty one, and
        # returning early without this check accepted it silently.
        _nothing_follows(text, at + 1)
        return []

    documents: list[bytes] = []
    while True:
        try:
            _, end = DECODER.raw_decode(text, at)
        except json.JSONDecodeError as broken:
            raise BulkError(f"Document {len(documents)} could not be read: {broken}") from broken

        documents.append(text[at:end].encode())

        at = _skip_space(text, end)
        if at >= len(text):
            raise BulkError("This batch ends in the middle of the array.")
        if text[at] == ",":
            at = _skip_space(text, at + 1)
            continue
        if text[at] == "]":
            _nothing_follows(text, at + 1)
            return documents
        raise BulkError(f"Expected ',' or ']' after document {len(documents) - 1}.")


def _nothing_follows(text: str, at: int) -> None:
    if _skip_space(text, at) != len(text):
        raise BulkError("There is more than one value in this batch.")


def _skip_space(text: str, at: int) -> int:
    while at < len(text) and text[at] in " \t\r\n":
        at += 1
    return at
