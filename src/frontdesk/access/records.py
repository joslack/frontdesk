"""A person's questions about their own records, asked in SQL and answered by the database as that person.

Nothing here decides what a person may read. The query runs on a connection that is signed in as their own login
role, and the grants and policies in frontdesk/db/schema.sql decide. What this adds is limits on a query a model
wrote: one statement, read-only, a time limit, and a result small enough to read.
"""

import hashlib
import hmac
import json
import time
import uuid
from pathlib import Path

import asyncpg

from frontdesk import settings
from frontdesk.db.connect import as_person

ROW_LIMIT = 200  # rows one query returns
RESULT_BUDGET = 8_000  # characters one result holds; a larger one is refused, not cut
EXPORT_ROW_LIMIT = 1_000_000
EXPORT_SECONDS = 60
LINK_SECONDS = 15 * 60  # how long the download link of an export works


class Refused(Exception):
    """The database refused the query, or it is not one this server runs. The text is for the caller to read."""


def refusal(e: asyncpg.PostgresError) -> Refused:
    if isinstance(e, asyncpg.InsufficientPrivilegeError):
        return Refused(f"Your role cannot read that: {e}. list_tables shows what you can read.")
    if isinstance(e, asyncpg.QueryCanceledError):
        return Refused("The query took too long and was stopped. Narrow it, or export it instead.")
    if isinstance(e, asyncpg.ReadOnlySQLTransactionError):
        return Refused("Queries here only read. To change something, open a request.")
    return Refused(f"SQL error: {e}")


async def tables(person: str) -> dict[str, dict]:
    """Every table and view this person can read: what it holds, its columns, and how many rows they can read."""
    async with as_person(person) as db, db.transaction(readonly=True):
        columns = await db.fetch(
            "SELECT c.table_name, c.column_name, c.data_type, obj_description(format('public.%I', c.table_name)::regclass) AS about "
            "FROM information_schema.columns c WHERE c.table_schema = 'public' ORDER BY c.table_name, c.ordinal_position")
        out: dict[str, dict] = {}
        for c in columns:
            table = out.setdefault(c["table_name"], {"about": c["about"], "rows": 0, "columns": []})
            table["columns"].append(f"{c['column_name']} {c['data_type']}")
        for name, table in out.items():  # the names come from the database's own catalog
            # A person with only some columns of a table cannot count with *, so count one they have.
            first = table["columns"][0].split()[0]
            table["rows"] = await db.fetchval(f'SELECT count("{first}") FROM "{name}"')
    return out


def shaped(found: list[dict]) -> list[dict] | dict:
    """The rows a query matched: the rows; or the first ROW_LIMIT with a note that there are more; or, when that is
    more text than RESULT_BUDGET, no rows and the size of what was asked for."""
    shown = found[:ROW_LIMIT]
    size = len(json.dumps(shown))
    if size > RESULT_BUDGET:
        return {"too_large": f"This query returns {len(found)}{'+' if len(found) > ROW_LIMIT else ''} rows and about {size:,} "
                             f"characters, and a result can hold {RESULT_BUDGET:,}. No rows were returned. Ask for less: narrow it "
                             "with WHERE, name only the columns you need, answer with COUNT, SUM or GROUP BY, or read it in pages "
                             "with ORDER BY, LIMIT and OFFSET. To hand the person every row, use export_csv with the same query."}
    if len(found) <= ROW_LIMIT:
        return found
    return {"rows": shown, "incomplete": f"Only the first {ROW_LIMIT} rows are here and the query matches more. Read the rest with "
                                         f"ORDER BY, LIMIT {ROW_LIMIT} and OFFSET, narrow the query, or use export_csv."}


async def query(person: str, sql: str) -> list[dict] | dict:
    """Run one read-only statement as this person."""
    try:
        async with as_person(person) as db, db.transaction(readonly=True):
            # A cursor stops reading one row past the limit, so a query that matches a million rows costs 201.
            found = await (await db.cursor(sql)).fetch(ROW_LIMIT + 1)
    except asyncpg.PostgresError as e:
        raise refusal(e) from e
    except asyncpg.InterfaceError as e:  # more than one statement, among others
        raise Refused(f"That is not one SQL query: {e}") from e
    return shaped(json.loads(json.dumps([dict(r) for r in found], default=str)))


def signature(export_id: str, expires: int) -> str:
    key = settings.env("EXPORT_SIGNING_KEY").encode()
    return hmac.new(key, f"{export_id}.{expires}".encode(), hashlib.sha256).hexdigest()


def link(export_id: str) -> str:
    """A link that downloads one export until it expires, for a browser that holds no token. The signature covers
    the export's id and the expiry, so neither can be changed."""
    expires = int(time.time()) + LINK_SECONDS
    return f"{settings.ACCESS_PUBLIC_URL}/exports/{export_id}.csv?expires={expires}&signature={signature(export_id, expires)}"


def file_of(export_id: str, expires: str, given: str) -> Path | None:
    """The file a download link names, or None when the link is not one this server signed or has expired."""
    try:
        export_id, expires_at = str(uuid.UUID(export_id)), int(expires)
    except ValueError:
        return None
    if expires_at < time.time() or not hmac.compare_digest(signature(export_id, expires_at), given):
        return None
    path = Path(settings.EXPORT_DIR) / f"{export_id}.csv"
    return path if path.exists() else None


async def export(person: str, sql: str) -> dict:
    """Write every row of a query to a CSV file, as this person, and return where to download it. The rows go from
    the database to the file; no model reads them."""
    export_id = str(uuid.uuid4())
    folder = Path(settings.EXPORT_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{export_id}.csv"
    try:
        async with as_person(person) as db:
            async with db.transaction(readonly=True):
                done = await db.copy_from_query(f"SELECT * FROM ({sql.strip().rstrip(';')}) AS export LIMIT {EXPORT_ROW_LIMIT}",
                                                output=str(path), format="csv", header=True, timeout=EXPORT_SECONDS)
            rows = int(done.split()[-1])
            await db.execute("SELECT record_export($1, $2, $3, $4)", uuid.UUID(export_id), sql, rows, path.stat().st_size)
    except asyncpg.PostgresError as e:
        path.unlink(missing_ok=True)
        raise refusal(e) from e
    return {"rows": rows, "bytes": path.stat().st_size, "download_url": link(export_id),
            "link_works_for_minutes": LINK_SECONDS // 60}
