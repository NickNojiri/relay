COMPOSE := docker compose -f infra/demo/compose.yml
OLLAMA_MODEL ?= llama3.2:1b

.PHONY: demo demo-ollama demo-logs demo-down demo-reset

## Full stack locally with the Echo provider: no API keys, no cloud spend.
demo:
	$(COMPOSE) up -d --build --wait
	@$(MAKE) --no-print-directory _urls

## Same stack, but the gateway calls a real local model through Ollama.
## First run downloads the Ollama image and the model (~1.3 GB for llama3.2:1b).
demo-ollama:
	DEMO_PROVIDER=ollama DEMO_MODEL=$(OLLAMA_MODEL) $(COMPOSE) --profile ollama up -d --build --wait
	$(COMPOSE) exec ollama ollama pull $(OLLAMA_MODEL)
	@$(MAKE) --no-print-directory _urls

demo-logs:
	$(COMPOSE) --profile ollama logs -f

## Stop containers; demo data is kept.
demo-down:
	$(COMPOSE) --profile ollama down

## Stop and wipe demo data; the next `make demo` re-seeds.
demo-reset:
	$(COMPOSE) --profile ollama down -v

.PHONY: _urls
_urls:
	@echo ""
	@echo "Relay demo is up."
	@echo "  Studio       http://localhost:3000   (start at /playground)"
	@echo "  Gateway      http://localhost:8000   (API key: demo-key)"
	@echo "  Sync server  ws://localhost:1234"
	@echo "Stop with 'make demo-down'; wipe data with 'make demo-reset'."
