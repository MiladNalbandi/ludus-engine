-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- The generated jsonb column, and why it is here rather than in V4.
--
-- `jsonb` and `generated always as (...) stored` are PostgreSQL. The slice tests run the shipped
-- migrations against H2 so that an entity which has drifted from its schema fails the build rather
-- than the deploy, and H2 cannot parse either construct.
--
-- Splitting it out keeps one shared schema instead of two hand-maintained dialects. What H2 loses
-- is a column nothing reads: `config` exists to be indexed and queried later, and the document is
-- only ever read back out of `config_json`. The byte-stability guarantee lives entirely in that
-- text column, so the tests that matter lose nothing by its absence.
--
-- It lives under db/vendor/{vendor} rather than db/migration/{vendor} because Flyway scans a
-- location recursively: a vendor directory nested inside db/migration is found by the plain
-- db/migration location too, and H2 then tries to run this and fails. Sibling directories, not
-- nested ones.

alter table wave
    add column config jsonb generated always as (config_json::jsonb) stored;

-- The queries this anticipates are "find content whose document contains X", which is what makes
-- a content type searchable without a column per field. Nothing issues one yet.
create index ix_wave_config on wave using gin (config);
