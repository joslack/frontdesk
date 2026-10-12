# Everything runs in a k3s cluster that colima starts in a virtual machine of its own, named frontdesk. Your other
# colima profile and your current Docker context are left alone.
#
#   make up        from nothing to everything running: cluster, secrets, base services, database, images, applications
#   make seed      put the demo records back as new, with every time counted from now
#   make images    build the three images again and restart what runs them
#   make status    what runs, and where to reach it
#   make agent     a Ghostty window with Claude Code as a customer's own agent, with Quillstack's tools only. It signs in
#                  with a browser; PERSON=dana signs in as dana with the demo password and no browser
#   make test      the tests that need the cluster's database
#   make down      stop the virtual machine; `make up` brings it back with its data
#   make destroy   delete the virtual machine and everything in it

K := kubectl --context colima-frontdesk -n frontdesk
UV := uv run --env-file .env
export DOCKER_CONTEXT := colima-frontdesk

.PHONY: up cluster secrets base database seed images apps status agent test down destroy

up: cluster secrets base database images apps status

cluster:
	colima status --profile frontdesk >/dev/null 2>&1 || colima start --profile frontdesk --kubernetes --cpu 4 --memory 6 --disk 30 --activate=false
	kubectl --context colima-frontdesk apply -f deploy/base/namespace.yaml

secrets:
	uv run python scripts/make_secrets.py
	uv run python scripts/cluster_secrets.py

base:
	uv run python scripts/realm.py
	kubectl --context colima-frontdesk apply -k deploy/base
	$(K) rollout status deploy/postgres deploy/keycloak --timeout=300s

database:
	$(UV) python -m frontdesk.db.setup
	$(UV) python -m frontdesk.db.seed

seed:
	$(UV) python -m frontdesk.db.seed

images:
	docker build -q -t frontdesk-app:dev .
	uv run langgraph build --config langgraph.jobs.json -t frontdesk-jobs:dev >/dev/null
	uv run langgraph build --config langgraph.desk.json -t frontdesk-desk:dev >/dev/null
	-$(K) rollout restart deploy/access deploy/dispatcher deploy/retention deploy/desk-api deploy/desk-queue deploy/jobs-api deploy/jobs-queue 2>/dev/null

apps:
	kubectl --context colima-frontdesk apply -k deploy/apps
	$(K) rollout status deploy/access deploy/dispatcher deploy/retention deploy/jobs-api deploy/jobs-queue deploy/desk-api deploy/desk-queue --timeout=300s

status:
	@$(K) get pods
	@echo
	@echo "access server (MCP)    http://localhost:18000/mcp"
	@echo "desk agent             http://localhost:18123    uv run --env-file .env frontdesk chat dana"
	@echo "a customer's own agent make agent                 then /mcp, quillstack, Authenticate"
	@echo "review                 uv run --env-file .env frontdesk review lena"
	@echo "retention desk (A2A)   http://localhost:18200    uv run --env-file .env python scripts/negotiate.py kenji --style patient"
	@echo "mail                   http://localhost:18025"
	@echo "Keycloak               http://localhost:18080    realm frontdesk"

agent:
	open -na Ghostty --args --title="A customer's own agent" -e "$(CURDIR)/scripts/their-agent.sh" $(if $(PERSON),--as $(PERSON))

test:
	$(UV) pytest -q

down:
	colima stop --profile frontdesk

destroy:
	colima delete --profile frontdesk
