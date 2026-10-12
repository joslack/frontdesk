"""Create the four databases and the roles that own the three that are a service's own state.

    uv run --env-file .env python -m frontdesk.db.setup

    quillstack  the company's records. frontdesk.db.seed fills it and makes its roles.
    desk        the conversation deployment's threads, checkpoints and memory, owned by desk_state
    jobs        the jobs deployment's threads, checkpoints and run queue, owned by jobs_state
    retention   the retention desk's conversations, owned by retention_state

Each service signs in as the owner of its own database and can open no other, so the conversation deployment
cannot read the records or the workers' state whatever its agent is talked into. Running this again
changes nothing that is already right. A database whose owner is wrong is dropped and made again, with its state.
"""

import asyncio

import asyncpg

from frontdesk import settings

STATE = {"desk": "DESK_STATE_PASSWORD", "jobs": "JOBS_STATE_PASSWORD", "retention": "RETENTION_STATE_PASSWORD"}


async def admin(database: str) -> asyncpg.Connection:
    return await asyncpg.connect(host=settings.DATABASE_HOST, port=settings.DATABASE_PORT, database=database,
                                 user="postgres", password=settings.env("POSTGRES_PASSWORD"))


async def setup() -> None:
    db = await admin("postgres")
    try:
        if not await db.fetchval("SELECT 1 FROM pg_database WHERE datname = 'quillstack'"):
            await db.execute("CREATE DATABASE quillstack")
        for name, password in STATE.items():
            owner = f"{name}_state"
            if not await db.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", owner):
                await db.execute(f"CREATE ROLE {owner} LOGIN")
            await db.execute(f"ALTER ROLE {owner} PASSWORD '{settings.env(password)}'")
            owned_by = await db.fetchval("SELECT r.rolname FROM pg_database d JOIN pg_roles r ON r.oid = d.datdba WHERE d.datname = $1", name)
            if owned_by != owner:
                await db.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
                await db.execute(f"CREATE DATABASE {name} OWNER {owner}")
            await db.execute(f"REVOKE CONNECT ON DATABASE {name} FROM PUBLIC")
            inside = await admin(name)
            try:
                # The server stores embeddings with pgvector, and only a superuser can add the extension.
                await inside.execute("CREATE EXTENSION IF NOT EXISTS vector")
            finally:
                await inside.close()
            print(f"{name}: owned by {owner}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(setup())
