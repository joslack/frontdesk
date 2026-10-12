"""Set the records database up and fill it with three workspaces.

    uv run --env-file .env python -m frontdesk.db.seed

It needs the databases that frontdesk.db.setup makes. It runs schema.sql, which drops and recreates everything, writes the records below, and gives each person in
frontdesk.people a login role. Every time in the records is counted back from the moment this runs, so a charge made
"three days ago" is three days old on the day of the seed and ages from there. Run it again to make the records
fresh.

The three workspaces are chosen so that a refund request on each has a different answer under the policy in
frontdesk/jobs/policy.md:

    acme    Team, monthly, 4 seats, $80. Renewed 3 days ago and nobody has used the product since: section 5 grants
            the renewal back in full.
    birch   Business, annual, 5 seats, $2,000. Renewed 10 days ago and in use since: section 6 grants an account
            credit for the months left, which is over $500, so section 11 sends it to a person.
    cobalt  Starter, monthly, 2 seats, $20. Renewed 12 days ago, in use since, three charges in all: nothing grants a
            refund.
"""

import asyncio
import calendar
import json
from datetime import UTC, datetime, timedelta
from itertools import count
from pathlib import Path

from frontdesk.db.connect import as_admin, principal_password
from frontdesk.people import PEOPLE, db_role
from frontdesk import settings

MONTHLY_PRICE = {"starter": 1000, "team": 2000, "business": 4000}  # cents for a seat
ANNUAL_MONTHS = 10  # a year costs ten months
SUPPORT = ("agt_lena", "Lena Fischer")


def add_months(at: datetime, n: int) -> datetime:
    month = at.month - 1 + n
    year, month = at.year + month // 12, month % 12 + 1
    return at.replace(year=year, month=month, day=min(at.day, calendar.monthrange(year, month)[1]))


class Workspace:
    """One workspace's records as rows for each table."""

    def __init__(self, key: str, name: str, tier: str, interval: str, seats: int, created: datetime):
        self.key, self.id, self.tier, self.interval, self.seats = key, f"ws_{key}", tier, interval, seats
        self.rows: dict[str, list[tuple]] = {}
        self._ids: dict[str, count] = {}
        self.add("workspaces", self.id, name, created, "active", None, f"cus_{key}")
        self.add("plan_history", self.id, tier, interval, seats, created)
        for person in (p for p in PEOPLE if p.workspace == key):
            joined = created if person.role == "owner" else created + timedelta(days=1)
            self.add("members", person.id, self.id, person.name, person.email, person.role, joined, None)

    def add(self, table: str, *row) -> None:
        self.rows.setdefault(table, []).append(row)

    def new(self, prefix: str) -> str:
        return f"{prefix}_{self.key}_{next(self._ids.setdefault(prefix, count(1))):03d}"

    def charge(self, at: datetime, reason: str = "subscription_cycle") -> str:
        """A paid invoice for the plan, and the period it pays for."""
        subtotal = MONTHLY_PRICE[self.tier] * (ANNUAL_MONTHS if self.interval == "year" else 1) * self.seats
        end = add_months(at, 12 if self.interval == "year" else 1)
        invoice = self.new("in")
        self.add("invoices", invoice, self.id, reason, at, at, end, subtotal, 0, 0, 0, subtotal, "paid", self.new("ch"),
                 f"pm_{self.key}_001")
        self.add("invoice_lines", invoice, self.id, f"Quillstack {self.tier.title()} ({self.interval}ly) x {self.seats}",
                 self.tier, self.interval, self.seats, subtotal)
        self.period = (at, end)
        return invoice

    def subscribe(self) -> None:
        self.add("subscriptions", f"sub_{self.key}_001", self.id, "active", *self.period, None)

    def session(self, person: str, at: datetime, actions: tuple[str, ...]) -> None:
        session = self.new("sess")
        for i, action in enumerate(actions):
            self.add("session_events", self.new("se"), self.id, f"usr_{person}", session, at + timedelta(minutes=4 * i), action)

    def activity(self, person: str, first: datetime, last: datetime, every: int, actions: tuple[str, ...], hour: int) -> None:
        """One session every `every` days from `first` up to `last`, at that hour."""
        day = first.replace(hour=hour, minute=10)
        while day <= last:
            self.session(person, day, actions)
            day += timedelta(days=every)

    def ticket(self, subject: str, by: str, at: datetime, status: str, messages: list[tuple[str, str]]) -> None:
        """`messages` are (author, body), where the author is a person's username or "support"."""
        ticket = self.new("tkt")
        names = {p.username: p.name for p in PEOPLE}
        self.add("tickets", ticket, self.id, subject, f"usr_{by}", at, status)
        for i, (author, body) in enumerate(messages):
            who = ("support_agent", *SUPPORT) if author == "support" else ("customer", f"usr_{author}", names[author])
            self.add("ticket_messages", ticket, *who, at + timedelta(hours=3 * i), body)


def workspaces(now: datetime) -> list[Workspace]:
    days = lambda n: timedelta(days=n)  # noqa: E731
    work = ("login", "view", "edit", "edit", "export")
    light = ("login", "view", "create")

    renewal = now - days(3)
    acme = Workspace("acme", "Acme Design", "team", "month", 4, add_months(renewal, -7))
    for back in range(7, -1, -1):
        acme.charge(add_months(renewal, -back), "subscription_create" if back == 7 else "subscription_cycle")
    acme.subscribe()
    quiet_from = renewal - days(1)  # the team has been away since the day before the renewal
    acme.activity("marcus", now - days(60), quiet_from, 1, work, 9)
    acme.activity("tom", now - days(59), quiet_from, 2, work, 10)
    acme.activity("priya", now - days(58), quiet_from, 5, light, 14)
    acme.activity("dana", now - days(57), quiet_from, 7, light, 16)
    acme.ticket("PDF export cuts off the last page", "tom", now - days(22), "solved", [
        ("tom", "Exports longer than 20 pages lose the final page. Screenshot attached."),
        ("support", "Thanks, Tom. We shipped a fix this morning; could you try again?"),
        ("tom", "Works now, thanks.")])
    acme.ticket("Cannot invite a guest reviewer", "marcus", now - days(6), "open", [
        ("marcus", "The invite dialog says our plan has no guest seats, but the pricing page says Team includes two."),
        ("support", "You are right that Team includes two guest seats. I have raised it with the team and will write back.")])
    acme.ticket("Copy of an earlier invoice", "priya", now - days(40), "solved", [
        ("priya", "Our accountant needs a PDF of the invoice from three months ago. Where do I find it?"),
        ("support", "Settings, Billing, Invoices has a download link on each row. I have also attached it here.")])

    renewal = now - days(10)
    birch = Workspace("birch", "Birch Analytics", "business", "year", 5, add_months(renewal, -12))
    birch.charge(add_months(renewal, -12), "subscription_create")
    birch.charge(renewal)
    birch.subscribe()
    birch.activity("grace", now - days(60), now - days(1), 1, work, 8)
    birch.activity("hugo", now - days(60), now - days(1), 1, work, 9)
    birch.activity("ines", now - days(59), now - days(1), 2, work, 11)
    birch.activity("elena", now - days(56), now - days(1), 7, light, 15)
    birch.activity("farid", now - days(50), now - days(1), 14, light, 13)
    birch.ticket("Dashboards are slow on large boards", "grace", now - days(15), "pending", [
        ("grace", "Boards with more than 500 cards take about ten seconds to open since last week."),
        ("support", "We can see it on our side too. A fix is in testing; I will update this ticket when it ships.")])
    birch.ticket("Single sign-on for our domain", "elena", now - days(70), "solved", [
        ("elena", "Can we turn on SAML sign-on for birch.example?"),
        ("support", "Yes, it is part of Business. I have enabled it; the setup guide is under Settings, Security.")])

    renewal = now - days(12)
    cobalt = Workspace("cobalt", "Cobalt Labs", "starter", "month", 2, add_months(renewal, -2))
    for back in range(2, -1, -1):
        cobalt.charge(add_months(renewal, -back), "subscription_create" if back == 2 else "subscription_cycle")
    cobalt.subscribe()
    cobalt.activity("lola", now - days(45), now - days(1), 1, work, 10)
    cobalt.activity("kenji", now - days(44), now - days(1), 3, light, 17)
    cobalt.ticket("Exporting a board to CSV", "lola", now - days(9), "solved", [
        ("lola", "Is there a way to export a board as CSV rather than PDF?"),
        ("support", "Yes: open the board menu, choose Export, then CSV.")])
    return [acme, birch, cobalt]


async def seed() -> None:
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    async with as_admin() as db:
        await db.execute((Path(__file__).parent / "schema.sql").read_text())
        for workspace in workspaces(now):
            for table, rows in workspace.rows.items():
                rows = [tuple(json.dumps(v) if isinstance(v, dict) else v for v in row) for row in rows]
                await db.copy_records_to_table(table, records=rows, columns=await columns(db, table, len(rows[0])))
        await db.execute(f"ALTER ROLE fd_jobs PASSWORD '{settings.env('JOBS_DB_PASSWORD')}'")
        await db.execute(f"ALTER ROLE fd_retention PASSWORD '{settings.env('RETENTION_DB_PASSWORD')}'")
        for person in PEOPLE:
            role = db_role(person.id)
            if await db.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role):
                await db.execute(f"DROP OWNED BY {role}; DROP ROLE {role}")
            # A person's role can sign in, belongs to the group for their role in the workspace, and owns nothing.
            await db.execute(f"CREATE ROLE {role} LOGIN PASSWORD '{principal_password(role)}' IN ROLE fd_{person.role} "
                             "CONNECTION LIMIT 10")
            await db.execute("INSERT INTO internal.principals VALUES ($1, $2)", role, person.id)
        tables = await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1")
        counts = {t["tablename"]: await db.fetchval(f"SELECT count(*) FROM {t['tablename']}") for t in tables}
    print(f"seeded as of {now:%Y-%m-%d %H:%M} UTC; {len(PEOPLE)} login roles")
    print("  " + ", ".join(f"{table} {n}" for table, n in counts.items()))


async def columns(db, table: str, n: int) -> list[str]:
    """The table's first n columns, in order: a row here leaves the trailing columns that have a default."""
    found = await db.fetch("SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                           "AND table_name = $1 ORDER BY ordinal_position", table)
    return [c["column_name"] for c in found][:n]


if __name__ == "__main__":
    asyncio.run(seed())
