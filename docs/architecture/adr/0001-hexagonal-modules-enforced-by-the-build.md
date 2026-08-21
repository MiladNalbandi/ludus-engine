# 1. Hexagonal modules, enforced by the build

- **Status:** accepted
- **Date:** 2026-08-21

## Context

Ludus is extracted from a feature inside a larger monorepo. That codebase declared a layered
architecture — `domain`, `application`, `infrastructure` — as a package naming convention, and
documented it. Over time its application layer came to depend directly on its persistence
classes: services took concrete database repositories rather than interfaces, so the dependency
arrow pointed the opposite way to the layer names.

Nobody did anything unreasonable. There was simply no moment at which the codebase said no.

That mattered for the extraction: with no interface at the seam, there was no way to swap the
persistence technology without editing every service, which is a large part of why the port is
a rewrite rather than a move.

## Decision

Separate Maven modules per layer, with the dependency direction expressed as module
dependencies, and two enforcement mechanisms:

1. `engine-domain` and `engine-application` declare no framework dependencies and ban them
   transitively via `maven-enforcer-plugin`. Violations are compile errors.
2. ArchUnit tests in `engine-bootstrap` cover dependency direction, framework types in the
   inner layers, outbound port usage, and field injection.

Both were verified by deliberately violating them.

## Consequences

Good: a violation is caught in seconds by the person who wrote it, with a message naming this
document. Application services are plain objects, so their tests need no Spring context and
run in milliseconds. The seam for swapping an adapter genuinely exists.

Costs, accepted: seven modules is more ceremony than one, and a Maven reactor build is slower
than a single-module one. Mapping between layers — domain type, JPA entity, web DTO — is real
work that a single annotated class would avoid.

That mapping cost is the one people argue about, and the honest answer is that it buys the
ability to change an HTTP field name, a column name, or a model concept independently. In a
project whose whole premise is a published contract that clients cache and a schema that
outlives any one release, keeping those three free to move separately is worth the boilerplate.

## Alternatives rejected

**A single module with package-level rules.** Cheaper, and ArchUnit alone would catch most
violations. Rejected because the strongest signal available — "this does not compile" — is only
available with real module boundaries, and because the codebase this replaces demonstrates
what happens when the rule is advisory.

**Layer-free, framework-annotated model classes.** Fastest to write and perfectly reasonable
for an application whose model, storage and API can change together. Rejected because they
cannot here: the wire format is a published contract with independent client implementations.
