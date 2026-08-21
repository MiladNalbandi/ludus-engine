# Architecture overview

Ludus is one Spring Boot application and one PostgreSQL database. No message broker, no second
service, no orchestrator required. That is a deliberate ceiling on operational cost: someone
should be able to run this on a small VM for a game that is not yet successful, and the design
should not punish them for it.

## The pieces

| | |
|---|---|
| **Engine** | Java 21 / Spring Boot. Owns content, validation, publication and player state. |
| **Editor** | A web application for authoring content. Arrives in `v0.3.0`. |
| **Your game** | Reads published content over HTTP and writes player state back. |
| **PostgreSQL** | The only datastore. Schema owned by Flyway. |

## Modules

```
engine-contracts          the wire schemas, packaged. No code.
engine-domain             pure Java: the model and the rules that do not need anything else
engine-application        use cases and the ports they talk through
engine-adapter-persistence  JPA, Flyway, outbound port implementations
engine-adapter-web          REST controllers, DTOs, OpenAPI
engine-adapter-security     JWT, API keys, filter chains
engine-bootstrap          the composition root and the runnable jar
```

Dependencies point inwards only: adapters know the application, the application knows the
domain, the domain knows nothing. `engine-bootstrap` is the only module that sees all of them,
and the only one that wires them together. See [hexagonal.md](hexagonal.md) for how that is
enforced.

## Two ideas worth understanding early

**Content is documents, not columns.** A wave, a level, a map — these are JSON documents
validated against a published JSON Schema. The database indexes what it needs to query
(identifier, name, order, publication state) and stores the document itself verbatim. The
schema, not a Java class, is the contract. That is what lets the content model grow without a
migration every time a behaviour gains a parameter, and what lets the editor and the game
client agree on a shape without either importing the other's code.

**Publication is separate from saving.** Editing content never affects players. Only published
content is served on the public routes, and to an unauthenticated client a draft is
indistinguishable from something that does not exist. This is one of the few places where the
design is deliberately unhelpful, and it is worth it: the alternative is that saving a
half-finished level ships it to everyone playing.

## Caching

Public content is cacheable and validated by ETag. The digest that produces those ETags is the
same function that produces the content hash a client polls to decide whether to refetch —
deliberately the same, because if the two are computed differently a client can be told
"something changed" by one signal while an HTTP cache serves it bytes validated by the other,
and the bug that produces is very hard to see.
