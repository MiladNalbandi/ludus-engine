"""The project's own JSON Schema for item attributes, read as the untrusted input it is.

The wave schema ships with the service and is as trustworthy as the build. This one is written
by whoever can edit a project, stored in a table, and run against every item on every save. So
it is read the way any other request body is: with limits, and with refusals for the things
that would make the engine do something on its author's behalf.

**A remote reference is refused.** `{"$ref": "https://attacker.example/s.json"}` would have the
engine fetch a URL of the author's choosing, from inside the deployment's network — server-side
request forgery, for anybody who can edit a schema. Only references that begin with `#`, which
point inside this same document, are accepted.

The Java looked for remote references with a regular expression over the text. Text is the
wrong place to look: `"\\u0024ref"` is the same key as `"$ref"` once parsed, and the pattern
does not see it. Here the document is parsed first and every reference keyword is read from
the parsed tree, so what is checked is exactly what the validator will act on.

**A schema is an object or a boolean, and nothing else.** That is what the specification says
a schema is. The Java's test for "a schema that is not a schema is refused" used a JSON array,
and its library accepted it, compiling it into a schema that validates nothing: every item
would pass and the project would believe it had validation. The test passed because it only
asked whether *something* was thrown. Here the shape is checked by this module, not left to
whatever a library happens to tolerate.

**It is capped**, in bytes and in depth, because it persists in a table and runs on every save.

What is not here is whether the schema means anything to a JSON Schema validator. That needs
the validator, and lives in an adapter behind `application.ports.SchemaValidator`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import documents
from .errors import Rejected, Violation, rejected

MAX_SCHEMA_BYTES = 64 * 1024

# One dialect, named, rather than whichever one a `$schema` claims. A schema written for
# draft-07 and validated by 2020-12 rules would quietly mean something else — `items` as a list
# is one of the differences — so a schema that asks for another dialect is told so.
DIALECT = "https://json-schema.org/draft/2020-12/schema"
ACCEPTED_DIALECTS = frozenset({DIALECT, f"{DIALECT}#"})

# Every keyword through which a schema can point somewhere else. `$recursiveRef` belongs to
# 2019-09 and is ignored by a 2020-12 validator; it is checked anyway, because a refusal that
# depends on knowing which keywords a library version still honours is one upgrade from a hole.
REFERENCE_KEYWORDS = ("$ref", "$dynamicRef", "$recursiveRef")

EMPTY = "{}"


@dataclass(frozen=True, slots=True)
class AttributeSchema:
    """The text exactly as the project sent it, and the schema it holds."""

    text: str
    document: dict[str, Any] | bool


def read(raw: bytes) -> AttributeSchema:
    """A schema the project may store, or every reason it may not, at its pointer.

    Pointers are into the schema itself, which is the whole request body: a refused reference
    is reported at `/properties/damage/$ref`, where the author can find it.
    """
    if len(raw) > MAX_SCHEMA_BYTES:
        raise rejected("", f"an item schema is at most {MAX_SCHEMA_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as broken:
        raise rejected("", f"an item schema is UTF-8 text: {broken}") from broken
    if not text.strip():
        raise rejected("", "send a schema, or {} for none")

    document = documents.parse("", text)
    if not isinstance(document, (bool, dict)):
        raise rejected(
            "",
            "an item schema is a JSON object, or true or false; this is "
            f"{_kind(document)}. A library that accepts it would compile it into a schema "
            "that validates nothing.",
        )

    found = documents.problems(document, "")
    found.extend(_dialect_problems(document))
    found.extend(reference_problems(document))
    if found:
        raise Rejected(found)
    return AttributeSchema(text=text, document=document)


def reference_problems(document: Any) -> list[Violation]:
    """Every reference in the schema that does not point inside it.

    The whole tree is walked, including places where a `$ref` key is data rather than a
    keyword — inside `const`, `enum` or `examples`. Telling the two apart means knowing every
    keyword of every dialect that holds an instance rather than a schema, and getting one wrong
    is a fetch. Refusing a remote-looking `$ref` that a validator would have ignored costs an
    author one edit; the other mistake costs the network.
    """
    found: list[Violation] = []
    for where, _, node in documents.nodes(document):
        if not isinstance(node, dict):
            continue
        for keyword in REFERENCE_KEYWORDS:
            if keyword not in node:
                continue
            target = node[keyword]
            if not isinstance(target, str) or not target.startswith("#"):
                found.append(
                    Violation(
                        f"{where}/{keyword}",
                        f"{target!r} is not a local reference. An item schema may only refer "
                        "inside itself, with a target beginning '#': a remote reference would "
                        "have the engine fetch a URL chosen by whoever wrote the schema, from "
                        "inside this deployment's network",
                    )
                )
    return found


def _dialect_problems(document: dict[str, Any] | bool) -> list[Violation]:
    if not isinstance(document, dict) or "$schema" not in document:
        return []
    if document["$schema"] in ACCEPTED_DIALECTS:
        return []
    return [
        Violation(
            "/$schema",
            f"item schemas are JSON Schema 2020-12; leave $schema out or set it to {DIALECT}",
        )
    ]


def _kind(value: Any) -> str:
    if isinstance(value, list):
        return "an array"
    if isinstance(value, str):
        return "a string"
    if value is None:
        return "null"
    return "a number"
