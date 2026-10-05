.PHONY: help setup up down restart logs seed test shell ollama-pull clean

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup: .env, services, models, seed data
	@bash scripts/bootstrap_local.sh

up: ## Start core services (API + DB + Redis + Worker)
	docker compose up -d

up-full: ## Start all services (Ollama + monitoring)
	docker compose --profile full --profile monitor up -d

down: ## Stop all services
	docker compose --profile full --profile monitor down

restart: ## Restart API and worker after code changes
	docker compose restart api celery_worker

logs: ## Tail API logs
	docker compose logs -f api

logs-worker: ## Tail worker logs
	docker compose logs -f celery_worker

seed: ## Load demo data (demo@example.com / demo123456)
	docker compose exec api python scripts/seed_demo_data.py

test: ## Run pytest in the API container
	docker compose exec api pytest tests/ -v

shell: ## Shell into API container
	docker compose exec api bash

ollama-pull: ## Pull Ollama models (bge-m3 + qwen2.5)
	@echo "Pulling bge-m3 embedding model..."
	docker compose exec -T ollama ollama pull bge-m3
	@echo "Pulling qwen2.5:3b chat model..."
	docker compose exec -T ollama ollama pull qwen2.5:3b

db-shell: ## PostgreSQL psql shell
	docker compose exec db psql -U postgres -d xplore_db

redis-cli: ## Redis CLI
	docker compose exec redis redis-cli

clean: ## Remove containers and volumes (deletes database data)
	docker compose --profile full --profile monitor down -v
	@echo "Clean complete. Run make setup to start fresh."
