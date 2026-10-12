#!/bin/bash
# Print the Authorization header for one demo person, as JSON. Claude Code runs this as the access server's
# headersHelper each time it connects, and again when a call is refused, so the session always has a live token.
#
#     scripts/token-header.sh dana
#
# A person's own agent signs them in with a browser, which scripts/their-agent.sh does by default. This stands in
# for that step where no person is there to do it, with the demo password.
set -euo pipefail
cd "$(dirname "$0")/.."
token=$(uv run --quiet --env-file .env python -m frontdesk.signin "${1:?which person}")
printf '{"Authorization": "Bearer %s"}\n' "$token"
