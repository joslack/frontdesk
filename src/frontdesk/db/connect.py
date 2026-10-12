"""Connections to the records database, one kind for each of the three things that connect to it.

    as_person  the access server, for one customer. It signs in as that person's own login role, so the database
               itself knows who is asking and applies their policies. The password of a person's role is derived
               from PRINCIPAL_SECRET and the role's name: the access server stores no password, and every replica
               of it derives the same one.
    as_jobs    the workers, the dispatcher and the review page, which read every workspace
    as_retention  the retention desk, which reads a workspace's plan and people and writes offers
    as_admin   setting the database up and seeding it, and nothing that serves a request
"""

import hashlib
import hmac
from contextlib import asynccontextmanager

import asyncpg

from frontdesk import settings
from frontdesk.people import db_role

STATEMENT_TIMEOUT_MS = 10_000


def principal_password(role: str) -> str:
    return hmac.new(settings.env("PRINCIPAL_SECRET").encode(), role.encode(), hashlib.sha256).hexdigest()


async def _connect(user: str, password: str, **server_settings) -> asyncpg.Connection:
    return await asyncpg.connect(host=settings.DATABASE_HOST, port=settings.DATABASE_PORT, database=settings.DATABASE_NAME,
                                 user=user, password=password, server_settings=server_settings)


@asynccontextmanager
async def as_person(person_id: str):
    """A connection that is this person's and no one else's. A person with no login role is refused by Postgres."""
    role = db_role(person_id)
    conn = await _connect(role, principal_password(role), application_name="frontdesk-access",
                          statement_timeout=str(STATEMENT_TIMEOUT_MS))
    try:
        yield conn
    finally:
        await conn.close()


@asynccontextmanager
async def as_jobs():
    conn = await _connect("fd_jobs", settings.env("JOBS_DB_PASSWORD"), application_name="frontdesk-jobs")
    try:
        yield conn
    finally:
        await conn.close()


@asynccontextmanager
async def as_retention():
    conn = await _connect("fd_retention", settings.env("RETENTION_DB_PASSWORD"), application_name="frontdesk-retention")
    try:
        yield conn
    finally:
        await conn.close()


@asynccontextmanager
async def as_admin():
    conn = await _connect("postgres", settings.env("POSTGRES_PASSWORD"), application_name="frontdesk-admin")
    try:
        yield conn
    finally:
        await conn.close()
