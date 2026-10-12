#!/bin/bash
# Claude Code as a customer's own agent: no built-in tools, no skills, no settings of yours, and one MCP server,
# which is Quillstack's access server.
#
#     scripts/their-agent.sh                         sign in with a browser, as a customer would
#     scripts/their-agent.sh --as dana               signed in as dana with the demo password, with no browser
#     scripts/their-agent.sh --as dana -p "..."      any further arguments go to claude
#
# The agent is not Quillstack's and Quillstack wrote none of its instructions. What it learns about working with
# Quillstack comes from the access server itself: the server's instructions, the tools' descriptions, and the
# skills it can read with read_skill.
#
# With a browser: the session starts with the line "1 MCP server needs authentication". Type /mcp, choose
# quillstack, which is below the built-in entry, and choose Authenticate. Keycloak's page opens; sign in as one of
# the people in src/frontdesk/people.py with the demo password, which is DEMO_PASSWORD in .env. Claude Code keeps
# the sign-in for the server's name and address, so the next session starts signed in; /mcp, quillstack, Clear
# authentication forgets it. Keycloak also keeps the browser signed in: to sign in as someone else, sign out at
# http://localhost:18080/realms/frontdesk/account first.
#
# It starts in a folder of its own, which stays empty, so that no project file reaches it. Claude Code asks once
# whether to trust that folder. The session may call the access server's tools without asking each time.
#
# Skills of yours stay out because, with no built-in tools, the session has no tool to load one with. The flag
# --disable-slash-commands would keep them out as well, and it would take /mcp away, which the sign-in needs.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${1:-}" = "--as" ]; then
    # Stands in for the browser: a helper fetches the person's token each time Claude Code connects.
    how="\"headersHelper\": \"$root/scripts/token-header.sh ${2:?which person}\""
    shift 2
else
    # frontdesk-cli is the client Keycloak knows, and 18765 is the port its sign-in answers on.
    how='"oauth": {"clientId": "frontdesk-cli", "callbackPort": 18765}'
fi
work="${XDG_CACHE_HOME:-$HOME/.cache}/quillstack-agent"
config="$(mktemp -t quillstack-mcp)"
mkdir -p "$work"
cat > "$config" <<JSON
{"mcpServers": {"quillstack": {"type": "http", "url": "http://localhost:18000/mcp", $how}}}
JSON
cd "$work"
exec claude --model claude-haiku-5-5 --tools "" --setting-sources "" --permission-mode manual \
    --strict-mcp-config --mcp-config "$config" --allowedTools "mcp__quillstack" "$@"
