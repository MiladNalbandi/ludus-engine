"""Batches: splitting an import back into its documents, and reading a list of ids to delete.

An import arrives as `[{…},{…},{…}]` — the documents joined with commas, untouched. Each one
has to be stored exactly as it was written, so the array cannot simply be parsed: parsing and
re-serialising the elements rewrites `2.0` as `2`, reorders keys, and moves the ETag of every
wave in the batch.

So the array is walked instead, and each element's byte range is sliced out of the original.
`raw_decode` does the hard part: it parses one value and reports where that value ended.
"""

from __future__ import annotations

import json
from typing import Any

from wavemaker.apps.content.domain.wave import Rejected
from wavemaker.platform.kernel.errors import PlatformError

DECODER = json.JSONDecoder()

# The most ids one batch delete may name. Enough for any real cleanup, and few enough that a
# refusal naming every missing one is still something a person can read.
MAX_BATCH = 50


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


def read_batch_ids(body: Any) -> tuple[str, ...]:
    """The ids a batch delete names, refused unless they are a known set.

    "Delete these six" is a statement about six particular waves. An empty list says nothing,
    and an id given twice means the caller's idea of the set is not the set they sent — both
    are refused rather than read generously, since the cost of a generous reading is deleted
    content.
    """
    if not isinstance(body, dict):
        raise Rejected("/: a batch delete is a JSON object with a list of ids.")
    ids = body.get("ids")
    if not isinstance(ids, list):
        raise Rejected("/ids: name the waves to delete as a list of ids.")
    if not ids:
        raise Rejected("/ids: name at least one wave to delete.")
    if len(ids) > MAX_BATCH:
        raise Rejected(f"/ids: at most {MAX_BATCH} waves may be deleted at once.")

    first_seen: dict[str, int] = {}
    for index, wave_id in enumerate(ids):
        if not isinstance(wave_id, str):
            raise Rejected(f"/ids/{index}: a wave is named by its id, as a string.")
        if wave_id in first_seen:
            raise Rejected(
                f"/ids/{index}: '{wave_id}' is already named at /ids/{first_seen[wave_id]}."
            )
        first_seen[wave_id] = index
    return tuple(ids)
