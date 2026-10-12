"""The people of the demo: who works where, in which role, and who reviews for Quillstack.

Two things are made from this list and have to agree: the Keycloak realm, which signs a person in, and the
database, which gives that person a login role and the rows they may read. scripts/realm.py writes the first and
frontdesk.db.seed the second.

A person belongs to one workspace and holds one role there:
    owner          every record of the workspace
    billing_admin  their own tickets and usage, the workspace's billing records, and usage as daily totals
    member         their own tickets and usage
"""

from dataclasses import dataclass
from hashlib import sha256

REALM = "frontdesk"
ROLES = ("owner", "billing_admin", "member")


@dataclass(frozen=True)
class Person:
    username: str  # what they sign in with
    name: str
    workspace: str
    role: str

    @property
    def id(self) -> str:
        return person_id(self.username)

    @property
    def email(self) -> str:
        return f"{self.username}@{self.workspace}.example"


PEOPLE = [
    Person("dana", "Dana Okafor", "acme", "owner"),
    Person("priya", "Priya Raman", "acme", "billing_admin"),
    Person("marcus", "Marcus Lee", "acme", "member"),
    Person("tom", "Tom Becker", "acme", "member"),
    Person("elena", "Elena Marsh", "birch", "owner"),
    Person("farid", "Farid Haddad", "birch", "billing_admin"),
    Person("grace", "Grace Liu", "birch", "member"),
    Person("hugo", "Hugo Stein", "birch", "member"),
    Person("ines", "Ines Duarte", "birch", "member"),
    Person("kenji", "Kenji Watanabe", "cobalt", "owner"),
    Person("lola", "Lola Ferrer", "cobalt", "member"),
]
BY_USERNAME = {p.username: p for p in PEOPLE}

# Quillstack's own people. They review what the workers propose and hold no role in any workspace.
REVIEWERS = {"lena": "Lena Fischer", "omar": "Omar Reyes"}


def person_id(username: str) -> str:
    return f"usr_{username}"


def db_role(person: str) -> str:
    """The Postgres login role of a person. Every role's name can be read in the catalog by any role, so the name
    is a hash and says nothing about who it is."""
    return "p_" + sha256(person.encode()).hexdigest()[:16]
