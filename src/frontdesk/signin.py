"""Get a token from Keycloak: for a demo person with their password, or for a service with its client secret.

    uv run --env-file .env python -m frontdesk.signin dana       # prints dana's token

A person's own agent signs them in with a browser. This is for the command line, the tests and the demo, where a
person's password is the demo password in .env.
"""

import sys
import time

import httpx

from frontdesk import settings

_held: dict[str, tuple[str, float]] = {}  # tokens by who they are for, each with the time it expires


async def _token(who: str, form: dict) -> str:
    token, expires = _held.get(who, ("", 0.0))
    if expires - time.time() < 60:
        async with httpx.AsyncClient(timeout=15) as http:
            answer = await http.post(settings.TOKEN_URL, data=form)
        if answer.status_code != 200:
            raise RuntimeError(f"Keycloak refused to sign {who} in: {answer.text}")
        token = answer.json()["access_token"]
        _held[who] = (token, time.time() + answer.json()["expires_in"])
    return token


async def as_person(username: str, password: str | None = None) -> str:
    return await _token(username, {"grant_type": "password", "client_id": "frontdesk-cli", "username": username,
                                   "password": password or settings.env("DEMO_PASSWORD")})


async def as_service() -> str:
    """The dispatcher's token, which carries the role "service". The jobs deployment accepts no other."""
    return await _token("service", {"grant_type": "client_credentials", "client_id": "frontdesk-service",
                                    "client_secret": settings.env("SERVICE_CLIENT_SECRET")})


async def as_desk() -> str:
    """The desk agent's own token, with the role "desk". It lets the agent list the access server's tools."""
    return await _token("desk", {"grant_type": "client_credentials", "client_id": "frontdesk-desk",
                                 "client_secret": settings.env("DESK_CLIENT_SECRET")})


if __name__ == "__main__":
    import asyncio

    print(asyncio.run(as_person(sys.argv[1])))
