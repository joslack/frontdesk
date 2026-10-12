"""Write deploy/base/realm.json, the Keycloak realm, from the people in src/frontdesk/people.py.

    uv run python scripts/realm.py

Keycloak imports the file when it starts and fills ${DEMO_PASSWORD} and the two client secrets from its environment,
so the file holds no secret.

    frontdesk-cli      a public client. A person signs in through it: with a browser, which is how a customer's own
                       agent such as Claude Code signs them in, or with their password from the command line.
    frontdesk-service  the dispatcher's identity when it calls the jobs deployment. Its tokens carry the role
                       "service", which is the only role the jobs deployment accepts.
    frontdesk-desk     the desk agent's own identity, with the role "desk". With it the agent lists the access
                       server's tools when it starts. It is no one's customer token, so no tool does anything for it,
                       and the jobs deployment refuses it.

Every token carries the audience "frontdesk" and the person's roles under realm_access.roles. The person is
preferred_username.
"""

import json
from pathlib import Path

from frontdesk.people import PEOPLE, REALM, REVIEWERS, ROLES

OUT = Path(__file__).resolve().parent.parent / "deploy/base/realm.json"
AUDIENCE = {"name": "audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper",
            "config": {"included.custom.audience": "frontdesk", "access.token.claim": "true", "id.token.claim": "false"}}


def user(username: str, name: str, email: str, roles: list[str]) -> dict:
    first, last = name.split(" ", 1)
    return {"username": username, "enabled": True, "emailVerified": True, "email": email, "firstName": first,
            "lastName": last, "realmRoles": roles,
            "credentials": [{"type": "password", "value": "${DEMO_PASSWORD}", "temporary": False}]}


realm = {
    "realm": REALM,
    "displayName": "Quillstack",  # what the sign-in page calls itself
    "enabled": True,
    "accessTokenLifespan": 3600,
    "ssoSessionIdleTimeout": 43200,
    "ssoSessionMaxLifespan": 86400,
    "roles": {"realm": [{"name": role} for role in (*ROLES, "reviewer", "service", "desk")]},
    "clients": [
        {"clientId": "frontdesk-cli", "publicClient": True, "standardFlowEnabled": True, "directAccessGrantsEnabled": True,
         "redirectUris": ["http://localhost:*", "http://127.0.0.1:*"], "webOrigins": ["+"], "protocolMappers": [AUDIENCE]},
        *({"clientId": f"frontdesk-{name}", "publicClient": False, "secret": f"${{{name.upper()}_CLIENT_SECRET}}",
           "standardFlowEnabled": False, "serviceAccountsEnabled": True, "protocolMappers": [AUDIENCE]} for name in ("service", "desk")),
    ],
    "users": [
        *(user(p.username, p.name, p.email, [p.role]) for p in PEOPLE),
        *(user(username, name, f"{username}@quillstack.example", ["reviewer"]) for username, name in REVIEWERS.items()),
        *({"username": f"service-account-frontdesk-{name}", "enabled": True, "serviceAccountClientId": f"frontdesk-{name}",
           "realmRoles": [name]} for name in ("service", "desk")),
    ],
}

if __name__ == "__main__":
    OUT.write_text(json.dumps(realm, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(OUT.parent.parent.parent)}: {len(realm['users'])} users")
