# ph27 business-ops. Every target is safe to run from a phone session (no prompts).
.PHONY: help test deploy-service deploy-workflow deploy status trial-claude backfill-fixed

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-16s %s\n", $$1, $$2}'

test: ## Run the full test suite
	uv run --quiet pytest -q

deploy-service: ## Rebuild/restart the ph27-bookkeeping container (picks up code + rules)
	docker compose up -d --build

deploy-workflow: ## Rebuild the n8n "ph27 Monthly Bills" workflow and import it (stays INACTIVE)
	uv run --quiet python n8n/build_monthly.py
	docker cp n8n/build/monthly_bills.json n8n:/tmp/m.json && docker exec -u root n8n chmod 644 /tmp/m.json
	docker exec n8n n8n import:workflow --input=/tmp/m.json; docker exec -u root n8n rm -f /tmp/m.json

deploy: test deploy-service deploy-workflow ## Test, then deploy service + workflow

status: ## Health of the service, broker, gateway activity and loaded models
	@docker exec n8n wget -q -O- http://ph27-bookkeeping:8091/health; echo " bookkeeping"
	@docker exec job-credentials wget -q -O- http://127.0.0.1:8090/health; echo " broker"
	@docker logs gateway --since 5m 2>&1 | grep -c "state=processing" | sed 's/^/agent sessions busy (5m): /'
	@ollama ps

trial-claude: ## Live trial: process the most recent Claude receipt into the ledger (needs MSG=<gmail id>)
	@test -n "$(MSG)" || (echo "usage: make trial-claude MSG=<gmail message id> TEXT='Amount paid \$$20.00' DATE=2026-09-21"; exit 1)
	@T=$$(grep ^BOOKKEEPING_TOKEN .env | cut -d= -f2); docker exec -e T=$$T n8n sh -c "wget -q -O- --header \"Authorization: Bearer \$$T\" --header 'Content-Type: application/json' --post-data '{\"email\":{\"id\":\"$(MSG)\",\"sender\":\"invoice+statements@mail.anthropic.com\",\"subject\":\"Your receipt from Anthropic\",\"date\":\"$(DATE)\",\"text\":\"$(TEXT)\"}}' http://ph27-bookkeeping:8091/process"; echo

backfill-fixed: ## Record fixed monthly rows for a range, safe to re-run (FROM=2026-01 TO=2026-09, same year)
	@test -n "$(FROM)" -a -n "$(TO)" || (echo "usage: make backfill-fixed FROM=2026-01 TO=2026-09"; exit 1)
	@T=$$(grep ^BOOKKEEPING_TOKEN .env | cut -d= -f2); \
	for mo in $$(uv run --quiet python -c "import sys; y,a=sys.argv[1].split('-'); b=sys.argv[2].split('-')[1]; print(' '.join(f'{y}-{m:02d}' for m in range(int(a), int(b)+1)))" $(FROM) $(TO)); do \
	  $(if $(DRY),echo "would post $$mo",docker exec -e T=$$T n8n sh -c "wget -q -O- --header \"Authorization: Bearer \$$T\" --header 'Content-Type: application/json' --post-data '{\"month\":\"'$$mo'\"}' http://ph27-bookkeeping:8091/fixed"; echo " $$mo"); \
	done
