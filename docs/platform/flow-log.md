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

| R   | Flow                                              | Ended at | Criteria | Tokens |  Cost |
| --- | ------------------------------------------------- | -------- | -------- | -----: | ----: |
| —   | _(scaffold and config: done by hand, not a flow)_ | —        | —        |      0 | $0.00 |

Nothing has run yet. Each row is added as its flow finishes.
