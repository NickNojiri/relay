.PHONY: demo demo-up demo-down demo-logs demo-clean demo-reset

# Build and start the full stack locally with Docker Compose
demo:
	@echo "🚀 Starting Relay stack (postgres + ollama + gateway + sync-server + studio)..."
	@echo "   Studio:      http://localhost:3000"
	@echo "   Gateway:     http://localhost:8000"
	@echo "   Sync server: ws://localhost:3001"
	@echo ""
	@echo "   Demo API key: demo-key-12345"
	@echo "   Database: postgresql://relay:relay@localhost:5432/relay"
	@echo ""
	@echo "   (Run 'make demo-logs' in another terminal to follow startup)"
	docker-compose up -d
	@echo ""
	@echo "Waiting for services to be ready..."
	@sleep 10
	@curl -s http://localhost:8000/health | jq . || echo "Gateway not yet ready, checking again..."
	@sleep 5
	@echo ""
	@echo "✅ Stack is up! Open http://localhost:3000 in your browser."
	@echo ""
	@echo "   Next steps:"
	@echo "   1. Create a prompt in /editor"
	@echo "   2. Create a flag in /flags"
	@echo "   3. Test in /playground"
	@echo ""
	@echo "   Stop with: make demo-down"

# Show live logs from all services
demo-logs:
	docker-compose logs -f

# Stop all services (keep volumes/data)
demo-down:
	docker-compose down
	@echo "✅ Stopped (data preserved)"

# Stop and remove everything (fresh start next time)
demo-clean:
	docker-compose down -v
	@echo "✅ Cleaned (volumes removed)"

# Restart a service (e.g., make demo-restart SERVICE=gateway)
demo-restart:
	docker-compose restart $(SERVICE)

# Show status of all services
demo-status:
	docker-compose ps

# Open studio in browser (macOS)
demo-open:
	open http://localhost:3000

.PHONY: build lint test typecheck

# Development targets (use pnpm directly)
build:
	turbo run build

lint:
	turbo run lint

test:
	turbo run test

typecheck:
	turbo run typecheck

clean:
	turbo run clean
	docker-compose down -v 2>/dev/null || true
