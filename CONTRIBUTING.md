# Contributing to Ludus

Thanks for considering it. Bug reports with a reproduction are as valuable as patches.

## Getting set up

You need **JDK 21**, **Docker** (for the integration tests), and **Node 20+** once the editor
lands.

```bash
./mvnw verify                 # everything: unit, architecture, integration
./mvnw -pl engine/engine-domain test    # one module
./mvnw -Dtest=SlugTest test             # one test
```

`docker compose -f deploy/docker-compose.yml up` runs the stack locally.

## The architecture rules

Ludus is a hexagonal codebase and the layering is enforced by the build, so a violation shows
up as a failing build rather than as review feedback. In short:

- **`engine-domain`** is plain Java. No Spring, no Jakarta, no Jackson, no ORM. If you need a
  framework type here, the design is wrong, not the rule.
- **`engine-application`** holds use cases and ports. It depends on the domain and nothing else.
  Services are plain objects with constructor injection, registered as beans in
  `engine-bootstrap`. That is what keeps their tests free of a Spring context.
- **Adapters** (`engine-adapter-*`) implement outbound ports and expose inbound ones. They may
  depend on the application; they must not depend on each other.
- **`engine-bootstrap`** is the only module with `@SpringBootApplication`, and the only place
  that knows about every adapter.

If a rule fires and you believe it is wrong, say so in the pull request — the rules are a
design decision and can be revised. Please do not add a suppression instead.

See [docs/architecture/hexagonal.md](docs/architecture/hexagonal.md) for the detail.

## Commits and pull requests

- **[Conventional Commits](https://www.conventionalcommits.org/)** for the title, e.g.
  `feat(content): serve published waves with an ETag`. The release notes are generated from
  them.
- Explain **why** in the body. What changed is visible in the diff; the reasoning is not.
- One logical change per pull request.
- New behaviour comes with a test. A bug fix comes with a test that fails without the fix.
- Update `CHANGELOG.md` under `## [Unreleased]`.

## Contributor Licence Agreement

Pull requests require signing a CLA, which is automated — a bot comments on your first pull
request with a link, and it takes a minute.

Being direct about why, because a CLA is friction and you deserve a real reason: Ludus is
AGPL-3.0 today, and the intention is a hosted service alongside the open-source project. A CLA
keeps relicensing and dual-licensing possible; without one, the project could never offer a
commercial tier containing community contributions, and could not fix a licensing mistake
later without tracking down every contributor. This is the same arrangement Grafana uses. The
CLA does **not** take your copyright away — you keep it, and you grant the project a licence.

## Reporting security issues

Please do not open a public issue. See [SECURITY.md](SECURITY.md).
