"""Give each deployment in the cluster the secrets it needs from .env, and no others.

    uv run python scripts/cluster_secrets.py

Each deployment reads one Secret, named after it. What a deployment holds is what it could misuse if a message
talked it into something, so the lists below are the boundary the design rests on: the desk holds no database
password for the records and no identity the jobs deployment accepts; the access server holds the key to sign in
as a customer and nothing that reads past a customer's own role.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KUBECTL = ["kubectl", "--context", "colima-frontdesk", "-n", "frontdesk"]
MODELS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "FIREWORKS_API_KEY"]
HOLDS = {
    "postgres": ["POSTGRES_PASSWORD"],
    "keycloak": ["KEYCLOAK_ADMIN_PASSWORD", "DEMO_PASSWORD", "SERVICE_CLIENT_SECRET", "DESK_CLIENT_SECRET"],
    # Signs in to the records database as the customer whose token it was shown, and signs export links.
    "access": ["PRINCIPAL_SECRET", "EXPORT_SIGNING_KEY"],
    # The desk agent: its models, its own identity for listing tools, and its own state database.
    "desk": ["LANGSMITH_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DESK_CLIENT_SECRET", "DESK_STATE_PASSWORD"],
    # The workers: their models, the role that reads every workspace and writes decisions, and their state database.
    "jobs": ["LANGSMITH_API_KEY", *MODELS, "JOBS_DB_PASSWORD", "JOBS_STATE_PASSWORD"],
    # The one identity the jobs deployment accepts, and the role that reads and moves requests.
    "dispatcher": ["SERVICE_CLIENT_SECRET", "JOBS_DB_PASSWORD"],
    # The retention desk: its model, the role that reads a workspace's plan and records an offer, and its own state.
    "retention": ["LANGSMITH_API_KEY", "ANTHROPIC_API_KEY", "RETENTION_DB_PASSWORD", "RETENTION_STATE_PASSWORD"],
}

if __name__ == "__main__":
    env = dict(line.split("=", 1) for line in (ROOT / ".env").read_text().splitlines() if "=" in line and not line.startswith("#"))
    for name, keys in HOLDS.items():
        made = subprocess.run([*KUBECTL, "create", "secret", "generic", name, "--dry-run=client", "-o", "yaml",
                               *(f"--from-literal={key}={env[key].strip()}" for key in keys)], check=True, capture_output=True)
        subprocess.run([*KUBECTL, "apply", "-f", "-"], input=made.stdout, check=True, capture_output=True)
        print(f"{name}: {', '.join(keys)}")
