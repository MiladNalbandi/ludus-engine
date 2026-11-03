"""The schema validator: `jsonschema`, told never to fetch anything.

**The library's default is to fetch.** A `jsonschema` validator built without a registry
resolves a reference it does not hold by downloading it, and only warns that it did. The
domain refuses every reference that does not begin with `#` before a schema gets here, and
this adapter does not rely on that: every validator it builds carries a registry whose only
way of retrieving a resource is to refuse. A reference that slipped past the first check
becomes an unresolvable reference, and a 422 — never a request leaving the building.

Local references are resolved when the schema is set, so one pointing at nothing is refused
then rather than on the first item an editor tries to save.
"""

from __future__ import annotations

import functools
import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import NoSuchResource, Unresolvable
from referencing.jsonschema import DRAFT202012

from ..domain.attribute_schema import AttributeSchema
from ..domain.errors import Rejected, SchemaUnusable, Violation, escape, rejected


def _refuse(uri: str) -> Resource[Any]:
    """The only way this registry retrieves a resource it does not hold."""
    raise NoSuchResource(ref=uri)  # type: ignore[call-arg]


# The meta-schemas the dialect itself refers to are bundled with the library and added by it
# on top of this, so validating needs nothing from the network either.
NO_RETRIEVAL: Registry[Any] = Registry(retrieve=_refuse)  # type: ignore[call-arg]

# A compiled validator per schema text. A project has one schema, so this holds a handful of
# entries in practice; the bound stops a stream of schema changes from growing it.
CACHE_SIZE = 32


class JsonSchemaValidator:
    def require_usable(self, schema: AttributeSchema) -> None:
        try:
            Draft202012Validator.check_schema(schema.document)
        except SchemaError as wrong:
            raise rejected(_pointer(wrong.absolute_path), wrong.message) from None
        except RecursionError:
            raise rejected("", "this schema is nested too deeply to check") from None
        found = [
            Violation(
                "",
                f"the reference {target!r} points at nothing in this schema",
            )
            for target in _unresolvable(schema.document)
        ]
        if found:
            raise Rejected(found)

    def violations(self, schema_text: str, document: Any) -> list[Violation]:
        try:
            problems = sorted(
                _compiled(schema_text).iter_errors(document),
                key=lambda problem: (_pointer(problem.absolute_path), problem.message),
            )
        # A schema is untrusted input and the library can be made to fail in more ways than it
        # documents: an unresolvable reference, a pattern Python cannot compile, nesting deeper
        # than the stack. Every one of them is the schema's problem, and a 422 saying so, never
        # a 500 for the editor who happened to save next.
        except Exception as broken:
            raise SchemaUnusable(str(broken) or type(broken).__name__) from broken
        return [_violation(problem) for problem in problems]


@functools.lru_cache(maxsize=CACHE_SIZE)
def _compiled(text: str) -> Draft202012Validator:
    """Keyed on the stored text rather than the parsed document, which is not hashable."""
    return Draft202012Validator(json.loads(text), registry=NO_RETRIEVAL)


def _unresolvable(document: dict[str, Any] | bool) -> list[str]:
    """Every reference in the schema that resolves to nothing, without fetching anything.

    Walked through the library's own idea of where subschemas are, so a `$id` partway down
    moves the base a reference resolves against exactly as it will during validation.
    """
    root = DRAFT202012.create_resource(document)
    pending = [(root, NO_RETRIEVAL.resolver_with_root(root))]
    missing: list[str] = []
    while pending:
        resource, resolver = pending.pop()
        contents = resource.contents
        if isinstance(contents, dict):
            for keyword in ("$ref", "$dynamicRef"):
                target = contents.get(keyword)
                if not isinstance(target, str):
                    continue
                try:
                    resolver.lookup(target)
                except Unresolvable:
                    missing.append(target)
        for child in resource.subresources():
            pending.append((child, resolver.in_subresource(child)))
    return sorted(missing)


def _violation(problem: ValidationError) -> Violation:
    return Violation(_pointer(problem.absolute_path), problem.message)


def _pointer(path: Any) -> str:
    return "".join(f"/{escape(step)}" for step in path)
