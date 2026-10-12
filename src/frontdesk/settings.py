"""Where each part finds the others, and its secrets, read from the environment.

On this machine the values come from .env and the defaults below, which are the ports the cluster's services answer
on. In the cluster the manifests in deploy/ set the addresses, and the Secret named frontdesk holds what .env holds.
"""

import os


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"{name} is not set. scripts/make_secrets.py writes it to .env; run with --env-file .env.")
    return value


# The records database.
DATABASE_HOST = env("DATABASE_HOST", "localhost")
DATABASE_PORT = int(env("DATABASE_PORT", "15432"))
DATABASE_NAME = "quillstack"

# Keycloak. A token names KEYCLOAK_ISSUER as its issuer wherever it is checked; KEYCLOAK_URL is how this process
# reaches Keycloak, which inside the cluster is another address.
REALM = "frontdesk"
KEYCLOAK_ISSUER = env("KEYCLOAK_ISSUER", f"http://localhost:18080/realms/{REALM}")
KEYCLOAK_URL = env("KEYCLOAK_URL", "http://localhost:18080")
JWKS_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/certs"
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
AUDIENCE = "frontdesk"

# The services, as this process reaches them.
ACCESS_URL = env("ACCESS_URL", "http://localhost:18000")  # the access server
ACCESS_PUBLIC_URL = env("ACCESS_PUBLIC_URL", "http://localhost:18000")  # the same, as a customer's browser reaches it
DESK_URL = env("DESK_URL", "http://localhost:18123")  # the conversation deployment
JOBS_URL = env("JOBS_URL", "http://localhost:18124")  # the jobs deployment
RETENTION_URL = env("RETENTION_URL", "http://localhost:18200")  # the retention desk
SMTP_HOST = env("SMTP_HOST", "localhost")
SMTP_PORT = int(env("SMTP_PORT", "1025"))

EXPORT_DIR = env("EXPORT_DIR", "exports")
