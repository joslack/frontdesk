"""Add to .env every secret this project makes for itself, each one once.

    uv run python scripts/make_secrets.py

.env already holds the model providers' keys and the LangSmith key. This adds what the cluster needs and no outside
service knows: passwords, the client secrets of the services, and the two signing keys. A value that is already in
.env stays as it is. scripts/cluster_secrets.py gives each deployment in the cluster the part of this file it needs.
"""

import secrets
from pathlib import Path

ENV = Path(__file__).resolve().parent.parent / ".env"
MADE_HERE = {
    "POSTGRES_PASSWORD": lambda: secrets.token_hex(16),
    "JOBS_DB_PASSWORD": lambda: secrets.token_hex(16),  # the workers' and reviewers' role on the records database
    "RETENTION_DB_PASSWORD": lambda: secrets.token_hex(16),  # the retention desk's role on the records database
    "RETENTION_STATE_PASSWORD": lambda: secrets.token_hex(16),  # owner of the retention desk's own database
    "DESK_STATE_PASSWORD": lambda: secrets.token_hex(16),  # owner of the conversation deployment's own database
    "JOBS_STATE_PASSWORD": lambda: secrets.token_hex(16),  # owner of the jobs deployment's own database
    "KEYCLOAK_ADMIN_PASSWORD": lambda: secrets.token_hex(12),
    "DEMO_PASSWORD": lambda: f"quill-{secrets.token_hex(3)}",  # every demo person signs in with it
    "SERVICE_CLIENT_SECRET": lambda: secrets.token_hex(24),  # the dispatcher's identity in Keycloak, which the jobs deployment accepts
    "DESK_CLIENT_SECRET": lambda: secrets.token_hex(24),  # the desk agent's own identity, which can list the access server's tools
    "PRINCIPAL_SECRET": lambda: secrets.token_hex(32),  # each person's database password is derived from it
    "EXPORT_SIGNING_KEY": lambda: secrets.token_hex(32),  # signs the download link of an export
}

if __name__ == "__main__":
    text = ENV.read_text() if ENV.exists() else ""
    have = {line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line and not line.startswith("#")}
    missing = {name: make() for name, make in MADE_HERE.items() if name not in have}
    if missing:
        with ENV.open("a") as f:
            f.write(("" if text.endswith("\n") or not text else "\n") + "\n# Made by scripts/make_secrets.py\n")
            f.writelines(f"{name}={value}\n" for name, value in missing.items())
    print(f"added {len(missing)} to .env: {', '.join(missing) or 'nothing'}")
