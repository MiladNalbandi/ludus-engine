"""Defining items, and setting the schema their attributes are checked against.

A project with no schema validates nothing, deliberately: a game that has not decided what its
items look like should not be stopped from creating one.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..domain import attribute_schema
from ..domain.errors import Rejected, SchemaUnusable, Violation, rejected
from ..domain.item import Item, draft_of
from .ports import Catalogue, SchemaValidator


def save_item(
    catalogue: Catalogue, validator: SchemaValidator, item_id: str, body: Mapping[str, Any]
) -> Item:
    """Create or replace an item, once its attributes satisfy the project's schema.

    Violations are reported at `/attributes` plus the pointer inside the document. The caller
    sent a whole item, so a violation at `/damage` would name a field their request does not
    have at the top level, and an editor mapping it onto a form would highlight nothing.
    """
    draft = draft_of(item_id, body)
    schema = catalogue.schema_text()
    if schema is not None:
        try:
            found = validator.violations(schema, draft.document)
        except SchemaUnusable as unusable:
            # Only possible for a schema written past this application, since one is checked
            # when it is set. It is the project's problem rather than the item's.
            raise rejected("", f"this project's item schema cannot be used: {unusable}") from None
        if found:
            raise Rejected(
                Violation(f"/attributes{problem.pointer}", problem.message) for problem in found
            )
    return catalogue.save(draft)


def replace_schema(catalogue: Catalogue, validator: SchemaValidator, raw: bytes) -> str:
    """Set the project's schema, refusing an unusable one now rather than on first use.

    Existing items are **not** re-validated. A project tightening its schema would otherwise
    find half its catalogue unsaveable with nothing saying which half; a migration is the honest
    way to handle that, not a failed request.
    """
    schema = attribute_schema.read(raw)
    validator.require_usable(schema)
    return catalogue.replace_schema(schema)
