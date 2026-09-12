-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- The generated jsonb column for app_config, PostgreSQL-only for the same reasons as V4.1: `jsonb`
-- and `generated always as (...) stored` are not H2 constructs, and this column exists to be
-- queried rather than read. The document itself is only ever read back out of config_json.

alter table app_config
    add column config jsonb generated always as (config_json::jsonb) stored;
