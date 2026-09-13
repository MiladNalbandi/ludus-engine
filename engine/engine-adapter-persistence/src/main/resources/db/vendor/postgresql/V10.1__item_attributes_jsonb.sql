-- SPDX-License-Identifier: AGPL-3.0-or-later
--
-- The generated jsonb column for item attributes, PostgreSQL-only for the same reasons as V4.1 and
-- V7.1. It exists to be queried -- "every item with fire damage" -- and the document itself is only
-- ever read back out of attributes_json.

alter table item
    add column attributes jsonb generated always as (attributes_json::jsonb) stored;

create index ix_item_attributes on item using gin (attributes);
