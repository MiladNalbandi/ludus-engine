# Security Policy

## Reporting a vulnerability

**Please do not open a public issue.**

Report privately through GitHub Security Advisories:
<https://github.com/miladnalbandi/ludus-engine/security/advisories/new>

You will get an acknowledgement within 72 hours and an assessment within 7 days. Fixes are
coordinated with you and disclosed publicly within 90 days of the report, or sooner once a fix
is released. If you would like credit in the advisory, say so — and if you would rather not be
named, that is fine too.

## Supported versions

| Version | Supported |
|---|---|
| `0.x` | Latest minor only |

Before `1.0.0`, only the most recent release receives fixes. A supported-branch policy starts
at `1.0.0`.

## Scope

In scope: the engine, the editor, the deployment manifests in `deploy/`, and the default
configuration a self-hoster gets from the quickstart.

Out of scope: findings that require a configuration the documentation explicitly warns
against, vulnerabilities in third-party dependencies with no exploitable path through Ludus
(report those upstream), and any deployment where an endpoint the documentation says to keep
internal — `/actuator/prometheus`, for instance — has been exposed publicly.

## What we ask of self-hosters

The engine refuses to start in production without a configured JWT signing secret, and its
default security posture is deny-by-default. Please do not work around either. The
[configuration reference](docs/operations/configuration.md) lists every setting that has a
security consequence.
