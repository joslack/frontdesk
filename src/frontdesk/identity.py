"""Who is calling, from the token Keycloak signed.

Every service here checks a token the same way: the signature against Keycloak's published keys, the issuer, the
audience "frontdesk", and the expiry. What it learns is the person's username and the roles the realm gives them.
Nothing a caller sends beside the token says who they are.
"""

import asyncio
from dataclasses import dataclass, field
from functools import cache

import jwt

from frontdesk import settings
from frontdesk.people import ROLES, person_id


class NotSignedIn(Exception):
    """The token is missing, expired, or not one Keycloak signed for this audience."""


@dataclass(frozen=True)
class Caller:
    username: str
    roles: frozenset[str]
    token: str = field(repr=False)

    @property
    def person_id(self) -> str:
        return person_id(self.username)

    @property
    def role(self) -> str | None:
        """The role this person holds in their workspace, or None for someone who is not a customer."""
        return next((r for r in ROLES if r in self.roles), None)


@cache
def _keys() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(settings.JWKS_URL, cache_keys=True, lifespan=600)


def verify(token: str) -> Caller:
    try:
        key = _keys().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=settings.AUDIENCE, issuer=settings.KEYCLOAK_ISSUER,
                            options={"require": ["exp", "iss", "aud"]})
    except jwt.PyJWTError as e:
        raise NotSignedIn(str(e)) from e
    return caller_of(claims, token)


def caller_of(claims: dict, token: str) -> Caller:
    """The caller a set of already verified claims describes."""
    return Caller(claims["preferred_username"], frozenset(claims.get("realm_access", {}).get("roles", [])), token)


def bearer(authorization: str | None) -> Caller:
    """The caller named by an Authorization header."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise NotSignedIn("Send the token as 'Authorization: Bearer <token>'.")
    return verify(token)


async def abearer(authorization: str | None) -> Caller:
    """The same from async code. Fetching Keycloak's keys blocks, so the check runs in a thread."""
    return await asyncio.to_thread(bearer, authorization)
