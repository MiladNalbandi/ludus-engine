# Hexagonal rules, and how they are enforced

A layered architecture that is only a naming convention decays. The codebase this one grew out
of had exactly these layer names and no enforcement, and its application layer ended up
importing its persistence layer — not through carelessness, but because nothing said no at the
moment it mattered.

So here the rules are executable. There are two mechanisms, and they cover different things.

## 1. The module graph (compile time)

`engine-domain` and `engine-application` declare no framework dependencies. Spring, Jakarta,
Jackson and Hibernate are not on their compile classpath, and `maven-enforcer-plugin` bans them
transitively as well. Importing Spring into the domain is therefore a **compile error**, not a
review comment — the fastest, least negotiable feedback available.

```
[ERROR] engine-application must not depend on a framework or on any adapter.
```

## 2. ArchUnit (test time)

The module graph cannot see dependency *direction* between packages that end up on the same
classpath, nor annotation use. `HexagonalArchitectureTest` covers:

| Rule | What it prevents |
|---|---|
| Layers depend inwards only | An adapter reaching into another adapter; anything reaching into the composition root |
| Domain knows nothing outside itself | The model quietly acquiring a dependency on a use case |
| Application does not know adapters | A use case reaching for a concrete repository instead of its port |
| No framework types in domain or application | A domain type becoming a storage or wire format by acquiring an annotation, after which it cannot change without breaking one of them |
| Outbound ports used only by the application and its adapters | The seam being bypassed |
| No field injection | Dependencies hidden from the constructor, and classes that cannot be tested without a container |

Those tests are written as plain JUnit tests that call `check()` rather than using
`@ArchTest` fields. The field style depends on ArchUnit's own JUnit engine being selected, and
when it is not, the class is still collected, still passes, and reports **zero tests** — a
suite that guards nothing while looking green. This was not hypothetical; it happened while
this file's first draft was being written. `importEngineClasses` additionally asserts that
classes from every layer were actually analysed, so the rules cannot pass vacuously either.

## Verifying the guardrails still bite

Both mechanisms were confirmed by deliberately violating them and watching the build fail. If
you change either, do the same — a guardrail nobody has seen fail is a guardrail nobody knows
works.

```java
// in engine-application: should fail the enforcer
public class Cheat { String x() { return org.springframework.util.StringUtils.capitalize("no"); } }

// in any adapter: should fail ArchUnit
@Component class Cheat { @Autowired private Thing thing; }
```

## Where things go

**A new use case** → an inbound port interface in `..application.<slice>.port.in`, a service
implementing it in `..application.<slice>`, registered as a bean in `engine-bootstrap`. The
service takes its collaborators through the constructor and has no annotations.

**Something the use case needs from outside** (a database, a clock, a file store, another
service) → an outbound port interface in `..application.<slice>.port.out`, implemented in an
adapter. The interface is written in the application's vocabulary, not the technology's.

**A rule that is true regardless of storage or transport** → the domain. If it needs a
framework to express, it is probably not a domain rule.

**HTTP shapes** → `engine-adapter-web`. Request and response DTOs never leave that module, and
domain types never enter it directly; a mapper sits between them. This is tedious exactly once
and pays for itself the first time an HTTP field has to be renamed without touching the model.
