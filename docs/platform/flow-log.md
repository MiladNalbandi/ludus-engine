# Flow log

Every keel flow run against this project: what it was for, how it ended, and what it cost.
Kept because a flow that stalls is only cheap if you can see what it spent before it stalled.

Costs are keel's own figures (`keel_budget`, `keel_flows`). A flow that is `stopped` or `waiting`
has already spent its tokens; the money is gone whether or not the work landed.

## Before WaveMaker

These ran while the project was Java, and are recorded as the starting balance rather than as
work on the platform.

| Flow                                                      | Ended at               | Criteria |        Tokens |       Cost |
| --------------------------------------------------------- | ---------------------- | -------- | ------------: | ---------: |
| feature "refactor all project to python and django"       | waiting · `red_stuck`  | 0/7      |       813,860 |      $4.98 |
| ludus-engine-my-workflow "Let's implement next version"   | **done** · `finish`    | 3/3      |     1,162,269 |      $6.03 |
| feature "ADD NEW FEATURE"                                 | stopped · `amend_gate` | 0/7      |     1,850,569 |      $8.76 |
| feature "add next feature"                                | stopped · `contract`   | 0/6      |     1,739,700 |      $3.60 |
| ludus-engine-my-workflow "I want you create new feature…" | stopped · `verify_red` | 0/3      |       420,743 |      $2.08 |
| feature "next step"                                       | stopped · `green`      | 0/7      |       511,596 |      $1.11 |
| feature "Next build"                                      | stopped · `spec_gate`  | 0/0      |       202,983 |      $0.59 |
| feature "test"                                            | stopped · `spec`       | 0/1      |       823,612 |      $0.83 |
| ludus-engine-my-workflow "implement next step"            | stopped · `start`      | 0/7      |       121,898 |      $0.66 |
| feature "sdasdas"                                         | stopped · `spec_gate`  | 0/0      |        29,195 |      $0.17 |
|                                                           |                        |          | **7,676,425** | **$28.81** |

One of ten finished. The pattern is worth reading before spending more: most of the money went
into flows that stopped at a gate, and the most expensive single flow, at $8.76, produced nothing.

### Why the Django flow could never finish

It is the one that matters for this plan, because it tried to do what WaveMaker now does.

It stalled at `red_stuck` on AC-5 and could not have stalled anywhere else. keel knew this project
as `kotlin-spring` with backend dir `engine/`, so `verify_red` ran

```
cd engine && ../mvnw -f .. -q test -Dtest=*AC-5*,*AC5*
```

for every criterion. The criteria were about a new Python project with pytest tests. No Java class
could ever be named `AC-5`, so the red step had no way to pass, and the flow spent $4.98 proving
it. The fix was not a better prompt. It was registering a Python stack and pointing `backend.dir`
at the Python project, which is done.

## WaveMaker

Every release shipped. Two kinds of agent did the work, and they are recorded separately because
only one of them is billed by keel.

### keel flows and side agents

keel's own figures (`keel_budget`, `keel_flows`, `keel_agents`). **$9.69, 2,325,602 tokens, and
nothing shipped through keel.**

| Work | keel | Ended at | Tokens | Cost | Outcome |
| --- | --- | --- | ---: | ---: | --- |
| #70 R2c — level authoring | `harness` flow | failed at `check` | 2,064,949 | $8.16 | Nothing usable. Every failure was environmental: keel's container on omarchy has no Docker socket, so the PostgreSQL tests could not start. Stopped by hand; the cap had already been raised once from 500,000. |
| The initiative, R2c → R9 | `goals-plan` flow | waiting at `plan_gate` | 83,203 | $0.49 | A sound plan. Its gate can only be answered by a person, in keel's Inbox. |
| #72 R4 — inventory | side agent (Sonnet) | idle | — | $0.61 | Stopped to ask about R3, believing it unmerged: keel's clone had not fetched. Not used. |
| #74 R6 — leaderboards | side agent (Sonnet) | idle | — | $0.44 | Same environment as #70; not used. |

The side agents ran on Sonnet, not the Opus that was asked for: changing the project's model needs
the owner's yes in keel's own form, and it was never given.

### Claude Code sub-agents and hand-built releases

On the owner's subscription, so they carry no keel cost; the token counts and durations are the
agents' own. Each landed as one PR through branch protection, with every check green.

| R | Built by | PR | Tokens | Time | Tests after |
| --- | --- | --- | ---: | ---: | ---: |
| R0 — core and plugin loader | hand | #64 | — | — | 30 |
| R1a — content read side | hand | #66 | — | — | 75 |
| R1b — PostgreSQL | hand | #67 | — | — | 99 |
| R2a — identity | hand | #68 | — | — | 124 |
| R2b — authoring, editor on Python | hand | #69 | — | — | 179 |
| R3 — players and economy | sub-agent | #82 | 273,571 | 27 min | 306 |
| R7 — media | sub-agent | #83 | 294,209 | 34 min | 446 |
| R2c — level authoring (#70) | sub-agent | #84 | 226,088 | 23 min | 523 |
| R4 — inventory | sub-agent | #86 | 327,371 | 34 min | 764 |
| R6 — leaderboards and progression | sub-agent | #87 | 299,782 | 39 min | 940 |
| R8 — editor shell, first half | sub-agent | #88 | 322,330 | 29 min | 155 editor |
| R5 — publish and install a plugin | sub-agent | #89 | 378,686 | 69 min | 1,083 |
| Rewards pay currency; #85 | sub-agent | #90 | 284,949 | 35 min | 1,158 |
| R8 — plugin screens, second half | sub-agent | #91 | 355,645 | 29 min | 1,200 / 198 editor |
| R9 — remove the Java | sub-agent | #92 | 470,727 | 43 min | 1,303 |

The same ticket, both ways: **#70 cost keel $8.16 and 2.06 million tokens and shipped nothing; a
sub-agent built it in 23 minutes and 226,088 tokens, with 77 tests, and it merged.**

### What made keel expensive here

All of it is the environment and setup, not the idea of keel, and it is written up as twelve
proposed keel-v2 changes. The three that account for most of the cost:

1. **No environment check before a flow builds.** keel retried an environment failure as if the
   code were wrong, and asked for more budget to do it again.
2. **keel's project clone on omarchy was 35 commits behind**, with nothing reporting it, so flows and
   side agents decided from stale code.
3. **Approvals this client could not show were reported as "you said no".**

keel was still worth having on the way: its dependency gate found a critical Next.js vulnerability
in the editor (#80), it caught a test signing key as a likely secret, and it kept every merged
migration untouched — which is why parallel releases were joined with merge revisions (`0004m`,
`0006m`) rather than by rewriting history.
