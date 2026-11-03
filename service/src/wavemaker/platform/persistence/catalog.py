"""What a database holds, read from PostgreSQL's own catalog, so a migration can be judged by
what it did rather than by what it said it would do.

A snapshot is taken before an app's migrations run and again after, inside the same
transaction. Every object outside the system schemas is listed with a fingerprint — a hash of
its columns, constraints, triggers, policies, rules, owner, grants and storage — so creating,
dropping and altering an object are all visible as a difference. The rows a transaction wrote
are counted too, from `pg_stat_xact_user_tables`, so an `UPDATE` of somebody else's table shows
up even though the schema did not change. `TRUNCATE` changes a table's `relfilenode`, which is
in the fingerprint.

The judgement is `judge`, a plain function over two snapshots: an app may create, change and
drop only what is its own, write rows only into its own tables, and create no schema, role,
extension, server or other cluster-wide object at all.

**What this cannot see:** rows *read* from another app's table, the value of a sequence that
is not the app's, and large objects. And a migration that ends its own transaction (`COMMIT`)
has made what came before it permanent; the runner notices the transaction changed and refuses,
but cannot take that part back.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from wavemaker.platform.kernel.permissions import is_own

# Indexes, and sequences owned by a column, belong to their table: `pk_inventory_item` is
# inventory's because `inventory_item` is, whatever the index is called.
DEPENDENT_KINDS = frozenset({"i", "I", "S"})

KIND_NAMES = {
    "r": "table",
    "p": "table",
    "v": "view",
    "m": "materialized view",
    "S": "sequence",
    "i": "index",
    "I": "index",
    "f": "foreign table",
    "c": "type",
}

USER_SCHEMAS = "n.nspname <> 'information_schema' and n.nspname not like 'pg\\_%'"

RELATIONS = text(
    f"""
    select n.nspname || '.' || c.relname as key,
           c.relname as name,
           c.relkind::text as kind,
           case
             when c.relkind in ('i', 'I') then (
               select tn.nspname || '.' || t.relname
               from pg_index x
               join pg_class t on t.oid = x.indrelid
               join pg_namespace tn on tn.oid = t.relnamespace
               where x.indexrelid = c.oid)
             when c.relkind = 'S' then (
               select tn.nspname || '.' || t.relname
               from pg_depend d
               join pg_class t on t.oid = d.refobjid
               join pg_namespace tn on tn.oid = t.relnamespace
               where d.classid = 'pg_class'::regclass and d.objid = c.oid
                 and d.refclassid = 'pg_class'::regclass and d.deptype in ('a', 'i')
               limit 1)
           end as belongs_to,
           md5(concat_ws(' | ',
             c.relfilenode, c.relowner, c.relacl, c.reloptions, c.relpersistence,
             c.relrowsecurity, c.relforcerowsecurity, obj_description(c.oid, 'pg_class'),
             (select string_agg(
                 a.attname || ':' || format_type(a.atttypid, a.atttypmod) || ':'
                   || a.attnotnull || ':' || coalesce(pg_get_expr(d.adbin, d.adrelid), '')
                   || ':' || a.attgenerated::text || ':' || a.attidentity::text || ':'
                   || coalesce(a.attacl::text, ''),
                 ',' order by a.attnum)
              from pg_attribute a
              left join pg_attrdef d on d.adrelid = a.attrelid and d.adnum = a.attnum
              where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped),
             (select string_agg(con.conname || ':' || pg_get_constraintdef(con.oid), ','
                                order by con.conname)
              from pg_constraint con where con.conrelid = c.oid),
             (select string_agg(pg_get_triggerdef(t.oid) || ':' || t.tgenabled::text, ','
                                order by t.tgname)
              from pg_trigger t where t.tgrelid = c.oid and not t.tgisinternal),
             (select string_agg(
                 p.polname || ':' || p.polcmd::text || ':' || p.polpermissive || ':'
                   || coalesce(pg_get_expr(p.polqual, p.polrelid), '') || ':'
                   || coalesce(pg_get_expr(p.polwithcheck, p.polrelid), ''),
                 ',' order by p.polname)
              from pg_policy p where p.polrelid = c.oid),
             (select string_agg(pg_get_ruledef(r.oid), ',' order by r.rulename)
              from pg_rewrite r where r.ev_class = c.oid),
             case when c.relkind in ('i', 'I') then pg_get_indexdef(c.oid) end,
             case when c.relkind in ('v', 'm') then pg_get_viewdef(c.oid) end
           )) as fingerprint
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where {USER_SCHEMAS}
    """
)

FUNCTIONS = text(
    f"""
    select n.nspname || '.' || p.proname
             || '(' || pg_get_function_identity_arguments(p.oid) || ')' as key,
           p.proname as name,
           md5(concat_ws(' | ', p.prosrc, p.probin, p.proowner, p.proacl, p.proconfig,
                         p.prosecdef, p.provolatile, p.prolang, p.prokind)) as fingerprint
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where {USER_SCHEMAS}
    """
)

TYPES = text(
    f"""
    select n.nspname || '.' || t.typname as key,
           t.typname as name,
           md5(concat_ws(' | ', t.typtype, t.typowner, t.typacl,
             (select string_agg(e.enumlabel, ',' order by e.enumsortorder)
              from pg_enum e where e.enumtypid = t.oid),
             (select string_agg(pg_get_constraintdef(con.oid), ',' order by con.conname)
              from pg_constraint con where con.contypid = t.oid)
           )) as fingerprint
    from pg_type t
    join pg_namespace n on n.oid = t.typnamespace
    where {USER_SCHEMAS}
      and t.typtype in ('b', 'd', 'e', 'r', 'm')
      and not exists (select 1 from pg_type a where a.typarray = t.oid)
    """
)

# Objects no app may create, drop or change: they belong to the database or the cluster, not
# to an app, and several of them are a way out — a foreign server reaches another database, a
# publication streams rows elsewhere, a role is a new identity.
CLUSTER = text(
    """
    select 'schema ' || n.nspname as key, md5(concat_ws('|', n.nspowner, n.nspacl)) as fp
      from pg_namespace n where n.nspname <> 'information_schema' and n.nspname not like 'pg\\_%'
    union all
    select 'extension ' || extname, md5(concat_ws('|', extversion, extnamespace, extowner))
      from pg_extension
    union all
    select 'event trigger ' || evtname, md5(concat_ws('|', evtevent, evtfoid, evtenabled, evttags))
      from pg_event_trigger
    union all
    select 'role ' || rolname, md5(concat_ws('|', rolsuper, rolinherit, rolcreaterole,
           rolcreatedb, rolcanlogin, rolreplication, rolbypassrls, rolconnlimit, rolvaliduntil,
           rolconfig))
      from pg_roles
    union all
    select 'membership of ' || member::regrole::text || ' in ' || roleid::regrole::text,
           md5(concat_ws('|', admin_option))
      from pg_auth_members
    union all
    select 'foreign data wrapper ' || fdwname, md5(concat_ws('|', fdwowner, fdwoptions, fdwacl))
      from pg_foreign_data_wrapper
    union all
    select 'foreign server ' || srvname, md5(concat_ws('|', srvowner, srvoptions, srvacl))
      from pg_foreign_server
    union all
    select 'publication ' || pubname,
           md5(concat_ws('|', puballtables, pubinsert, pubupdate, pubdelete, pubtruncate))
      from pg_publication
    union all
    select 'setting for database ' || setdatabase || ' role ' || setrole, md5(setconfig::text)
      from pg_db_role_setting
    union all
    select 'default privileges of ' || defaclrole::regrole::text || ' on ' || defaclobjtype::text
             || ' in ' || defaclnamespace, md5(defaclacl::text)
      from pg_default_acl
    union all
    select 'language ' || lanname, md5(concat_ws('|', lanowner, lanpltrusted, lanacl))
      from pg_language
    union all
    select 'cast ' || castsource::regtype::text || ' as ' || casttarget::regtype::text,
           md5(concat_ws('|', castfunc, castcontext, castmethod))
      from pg_cast where oid >= 16384
    """
)

WRITES = text(
    """
    select schemaname || '.' || relname as key, n_tup_ins + n_tup_upd + n_tup_del as rows
    from pg_stat_xact_user_tables
    """
)


@dataclass(frozen=True, slots=True)
class Relation:
    name: str
    kind: str
    belongs_to: str | None
    fingerprint: str

    @property
    def kind_name(self) -> str:
        return KIND_NAMES.get(self.kind, "relation")


@dataclass(frozen=True, slots=True)
class Named:
    name: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class Snapshot:
    relations: dict[str, Relation]
    functions: dict[str, Named]
    types: dict[str, Named]
    cluster: dict[str, str]
    writes: dict[str, int]


@dataclass(slots=True)
class Judgement:
    """What an app's migrations did that it may not do, and what it now owns."""

    refused: list[str] = field(default_factory=list)
    created: set[str] = field(default_factory=set)
    dropped: set[str] = field(default_factory=set)


def snapshot(connection: Connection) -> Snapshot:
    return Snapshot(
        relations={
            row.key: Relation(row.name, row.kind, row.belongs_to, row.fingerprint)
            for row in connection.execute(RELATIONS)
        },
        functions={
            row.key: Named(row.name, row.fingerprint) for row in connection.execute(FUNCTIONS)
        },
        types={row.key: Named(row.name, row.fingerprint) for row in connection.execute(TYPES)},
        cluster={row.key: row.fp for row in connection.execute(CLUSTER)},
        writes={row.key: int(row.rows) for row in connection.execute(WRITES)},
    )


def relation_object(key: str) -> str:
    return f"relation {key}"


def function_object(key: str) -> str:
    return f"function {key}"


def type_object(key: str) -> str:
    return f"type {key}"


def judge(before: Snapshot, after: Snapshot, prefix: str, owned: Iterable[str]) -> Judgement:
    """Everything that changed between two snapshots, held against what the app owns.

    `owned` is the app's objects as recorded by earlier runs. An object created now is the
    app's when its name carries the app's prefix. An object that existed before and is not in
    `owned` is somebody else's even when its name carries the prefix: a plugin called `api`
    does not own the platform's `api_key` table.
    """
    owned = set(owned)
    result = Judgement()
    _judge_relations(before, after, prefix, owned, result)
    _judge_named(before.functions, after.functions, prefix, owned, function_object, result)
    _judge_named(before.types, after.types, prefix, owned, type_object, result)

    for key in sorted(set(before.cluster) | set(after.cluster)):
        was, now = before.cluster.get(key), after.cluster.get(key)
        if was == now:
            continue
        verb = "creates" if was is None else "drops" if now is None else "changes"
        result.refused.append(f"{verb} {key}")

    mine = (owned | result.created) - result.dropped
    for key in sorted(after.writes):
        if after.writes[key] > before.writes.get(key, 0) and relation_object(key) not in mine:
            result.refused.append(f"writes rows of table {key}")
    return result


def _judge_relations(
    before: Snapshot, after: Snapshot, prefix: str, owned: set[str], result: Judgement
) -> None:
    created = set(after.relations) - set(before.relations)
    # The independent objects first, so an index can be judged by whether its table is now
    # the app's.
    for key in sorted(created):
        relation = after.relations[key]
        if relation.kind in DEPENDENT_KINDS and relation.belongs_to is not None:
            continue
        if is_own(relation.name, prefix):
            result.created.add(relation_object(key))
        else:
            result.refused.append(
                f"creates {relation.kind_name} {key}, outside its prefix '{prefix}'"
            )

    mine = owned | result.created

    def own(relation: Relation, key: str) -> bool:
        if relation.kind in DEPENDENT_KINDS and relation.belongs_to is not None:
            return relation_object(relation.belongs_to) in mine
        return relation_object(key) in mine

    for key in sorted(created):
        relation = after.relations[key]
        dependent = relation.kind in DEPENDENT_KINDS and relation.belongs_to is not None
        if dependent and not own(relation, key):
            result.refused.append(
                f"creates {relation.kind_name} {key} on {relation.belongs_to}, "
                "a table it does not own"
            )

    for key in sorted(set(before.relations) - set(after.relations)):
        relation = before.relations[key]
        if own(relation, key):
            result.dropped.add(relation_object(key))
        else:
            result.refused.append(f"drops {relation.kind_name} {key}, which it does not own")

    for key in sorted(set(before.relations) & set(after.relations)):
        was, now = before.relations[key], after.relations[key]
        if was.fingerprint != now.fingerprint and not own(now, key):
            result.refused.append(f"alters {now.kind_name} {key}, which it does not own")


def _judge_named(
    before: dict[str, Named],
    after: dict[str, Named],
    prefix: str,
    owned: set[str],
    describe: Callable[[str], str],
    result: Judgement,
) -> None:
    for key in sorted(set(after) - set(before)):
        if is_own(after[key].name, prefix):
            result.created.add(describe(key))
        else:
            result.refused.append(f"creates {describe(key)}, outside its prefix '{prefix}'")
    for key in sorted(set(before) - set(after)):
        if describe(key) in owned:
            result.dropped.add(describe(key))
        else:
            result.refused.append(f"drops {describe(key)}, which it does not own")
    for key in sorted(set(before) & set(after)):
        if before[key].fingerprint != after[key].fingerprint and describe(key) not in owned:
            result.refused.append(f"alters {describe(key)}, which it does not own")
