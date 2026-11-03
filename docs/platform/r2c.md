# R2c — level authoring, and batch delete

Owed from R2b. Levels could be listed and activated, and nothing else: the two levels in the
R2b screenshot were seeded with SQL, and a backend where a level can only be made with SQL is
not one anybody else can run. Deleting many waves at once was also missing from the admin
surface.

Nothing new in the schema. The tables, the composite foreign key and the partial unique index
were all in `0001_content.py` already; this release is routes that respect them.

## Acceptance criteria

|          | Criterion                                                                                       | State |
| -------- | ----------------------------------------------------------------------------------------------- | ----- |
| **AC-1** | A level names waves in order, drafts included, and reports each member's `published` state     | green |
| **AC-2** | A level cannot list a wave twice or put two waves at one position: a 422 naming it, never a 500 | green |
| **AC-3** | A wave not in this project is a 422 naming its position; the composite key's refusal is too    | green |
| **AC-4** | **Replacing a level ends with exactly the new list or the old one**, under twelve at once too   | green |
| **AC-5** | Deleting a level never deletes its waves; deleting the active level leaves none active          | green |
| **AC-6** | A batch delete is all or nothing: one unknown id deletes nothing and is named                   | green |
| **AC-7** | An unknown or malformed level id is a 404, on every level route including activate              | green |
| **AC-8** | Writes are for editors and administrators; a viewer may read a level; no token is a 401         | green |

## The contract

All five operations are served at the paths `docs/api/openapi-v1.json` gives them, under its
operation ids and with its field names. A test reads the document and the served
`/openapi.json` side by side, so a renamed route or field fails here rather than in a
generated client.

| Operation          | Route                                    | Answers                         |
| ------------------ | ---------------------------------------- | ------------------------------- |
| `createWaveLevel`  | `POST /api/v1/admin/wave-levels`         | 201, `WaveLevelSummary`         |
| `getWaveLevel`     | `GET /api/v1/admin/wave-levels/{id}`     | 200, `WaveLevelSummary`, or 404 |
| `updateWaveLevel`  | `PUT /api/v1/admin/wave-levels/{id}`     | 200, `WaveLevelSummary`, or 404 |
| `deleteWaveLevel`  | `DELETE /api/v1/admin/wave-levels/{id}`  | 204, or 404                     |
| `batchDeleteWaves` | `POST /api/v1/admin/waves/batch-delete`  | 200, `WaveBatchDeleteResult`    |

**The same deliberate difference as R2 and R7:** the document lists `200` for create and
delete, because springdoc writes the default when an annotation says nothing. The Java engine
answered `201` and `204`, and so does every other content route here.

The level routes now name their path parameter `id`, as the document does. `listWaveLevels`
and `activateWaveLevel` were given their operation ids at the same time; the older wave routes
still carry FastAPI's generated ones.

## A level is a list

```
  PUT /wave-levels/{id}   {"name": "Act One", "waves": ["second", "draft", "first"]}
                                                          |        |        |
  wave_level_wave                                         v        v        v
    (level, wave, position)                           (L, second, 0) (L, draft, 1) (L, first, 2)
```

The order is the list order. Nothing an author sends carries a position: a position beside a
list is a second source for one fact, and the two drift the first time somebody reorders by
editing one of them. The column exists because a table has no order of its own, and it is
written from the indices.

A replacement is wholesale. A field left out is cleared rather than kept — except `waves`,
which is required, because a client that forgot it would otherwise empty a level it only meant
to rename.

## Three rules, checked twice

Each rule is checked before the write, so an author is told which entry to change, and kept by
the database, so it holds when the check is missed.

| Rule                                   | Checked by                          | Kept by                       | Answer                 |
| -------------------------------------- | ----------------------------------- | ----------------------------- | ---------------------- |
| A wave appears in a level once         | `LevelDraft.read`                   | `pk_wave_level_wave`          | 422 `/waves/2`         |
| One wave per position                  | positions come from list indices    | `uq_wave_level_wave_position` | 422 `/waves`           |
| A member is a wave of the same project | a lookup in the write's transaction | `fk_wave_level_wave_wave`     | 422 `/waves/1`, each   |

When a constraint does fire, the store reads the constraint's name from the error's
diagnostics — not its message, which a locale or a new PostgreSQL version can reword — and
turns each of the three into a rejection. Any other violation goes up unchanged: it is a
fault, and dressing it as an author's mistake would hide it.

The existence lookup holds the waves it found `for share` until the transaction ends, so none
of them can be deleted between the check and the insert that relies on it. The tests go round
both checks on purpose — a draft with a repeated wave written straight to the store, and an
existence check made to miss once — because through the routes the constraints never fire,
and a translation nobody has seen work is one nobody knows works.

A wave of another project is not found by the lookup, which filters on the project, so it is
reported as missing like any other. The composite key would refuse it anyway.

## Replacing a level while somebody else does

```
  A: update wave_level ... where id = L     -- takes L's row lock
  B: update wave_level ... where id = L     -- waits for A
  A: delete members of L; insert A's list; commit
  B:                                        -- wakes; its next statement sees A's members
  B: delete members of L; insert B's list; commit
```

The level's own row is updated first, and that order is the behaviour. Deleting the members
first lets both replacements delete the old rows, both insert from position 0, and collide.

This was checked by breaking it. With the member writes moved ahead of the row update, eleven
of twelve concurrent replacements were refused with "this list names one wave twice" — which
none of them had sent. The concurrency test runs twelve threads in a database of its own and
asserts that every one is answered with a level, that the name and the waves at the end come
from the same request, and that there is one wave per position and nothing left over.

## Deleting

**A level.** One statement. The membership rows go with it by foreign key; the waves are not
touched. `active` is a column on the row that went, so deleting the active level leaves none
active, and the public `GET /wave-levels/active` answers 404. Nothing promotes another level
in its place: which one would be a guess, and a wrong guess ships a level to every player.

**Many waves.** One `delete ... returning wave_id`, then a look at what came back. If any id
removed nothing, the transaction is rolled back and every unknown id is named:

```
422  /ids/1: there is no wave 'ghost' in this project; /ids/3: there is no wave 'phantom' ...
```

"Delete these six" is a statement about six known waves, and a caller with a typo has a
different catalogue than they think — better learned now than from the five that went. For the
same reason an empty list and an id named twice are refused rather than read generously, and a
batch is at most fifty ids, as in the Java. Deleted waves leave every level they were in.

## A bug the tests found

**Activating a level with an id that is not a UUID was a 500**, on main since R2b. The string
went to PostgreSQL as it came, and the cast to `uuid` failed there. Every level route now
parses the id first and answers a malformed one exactly as an unknown one, a 404 — telling
them apart would say which ids are well formed, which nobody can act on.

Reading that route also turned up a smaller one: after activating, it found the level again by
comparing id strings, so an id sent in upper case activated the level and then answered 404. It
now looks the level up by the parsed id. That one has no test of its own.

## Errors

- **400** the body is not JSON.
- **422** it is JSON and not acceptable, with a pointer: `/name`, `/description`, `/waves`,
  `/waves/2`, `/ids/1`. Every missing wave is named, not the first.
- **404** no such level, or an id that cannot be one.
- **401** no token; **403** a viewer writing.

## Still owed

- **Two concurrent edits touching the same waves in opposite orders can deadlock.** A level
  replacement holds its waves `for share` and a batch delete takes them exclusively; neither
  takes its row locks in a fixed order, so a replacement that has locked B and wants C, and a
  delete that has locked C and wants B, each wait for the other. PostgreSQL breaks the cycle by aborting one, which reaches the client as
  a 500. Locking in `wave_id` order on both paths would remove it. There is no test, because
  making it happen on demand needs a way to pause between statements that this code does not
  have.
- The editor still only lists and activates levels. These routes are there for it.
- The older wave routes serve FastAPI's generated operation ids rather than the contract's.
