#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}[1/5] Initializing .env...${NC}"

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo -e "${GREEN}  ✓ Created .env from .env.example${NC}"

  # Generate a random SECRET_KEY
  if command -v openssl &>/dev/null; then
    NEW_SECRET=$(openssl rand -hex 32)
    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s/^SECRET_KEY=.*/SECRET_KEY=${NEW_SECRET}/" .env
    else
      sed -i "s/^SECRET_KEY=.*/SECRET_KEY=${NEW_SECRET}/" .env
    fi
    echo -e "${GREEN}  ✓ Generated random SECRET_KEY${NC}"
  else
    echo -e "${YELLOW}  ⚠ openssl not found; SECRET_KEY left at default (replace in production)${NC}"
  fi
else
  echo -e "${GREEN}  ✓ .env already exists, skipping${NC}"
fi

echo -e "${CYAN}[2/5] Starting core services (API + DB + Redis + Worker)...${NC}"
docker compose up -d --build

echo -e "${CYAN}[3/5] Waiting for API to become ready...${NC}"
MAX_WAIT=60
WAITED=0
until curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; do
  sleep 2
  WAITED=$((WAITED + 2))
  if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${YELLOW}  ⚠ API startup timed out; check: docker compose logs api${NC}"
    break
  fi
done
if [ $WAITED -lt $MAX_WAIT ]; then
  echo -e "${GREEN}  ✓ API is ready${NC}"
fi

echo -e "${CYAN}[4/5] Seeding demo data...${NC}"
docker compose exec -T api python scripts/seed_demo_data.py 2>/dev/null || \
  echo -e "${YELLOW}  ⚠ Demo seed failed; run manually: make seed${NC}"

echo -e "${CYAN}[5/5] Checking Ollama...${NC}"
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo -e "${GREEN}  ✓ Ollama is running${NC}"

  # Check whether bge-m3 is present
  if docker compose exec -T ollama ollama list 2>/dev/null | grep -q "bge-m3"; then
    echo -e "${GREEN}  ✓ bge-m3 model is ready${NC}"
  else
    echo -e "${YELLOW}  → Pulling bge-m3 (first download may take a while)...${NC}"
    docker compose exec -T ollama ollama pull bge-m3 || \
      echo -e "${YELLOW}  ⚠ Model pull failed; run: make ollama-pull${NC}"
  fi
else
  echo -e "${YELLOW}  ⚠ Ollama is not running; RAG is unavailable${NC}"
  echo -e "${YELLOW}    Start full stack: make up-full${NC}"
  echo -e "${YELLOW}    After Ollama is up: make ollama-pull${NC}"
fi

# Detect mock vs live LLM mode
LLM_KEY=$(grep -E "^LLM_API_KEY=" .env 2>/dev/null | cut -d'=' -f2- || echo "")
if [ -z "$LLM_KEY" ]; then
  MOCK_MODE="${YELLOW}Mock mode (no API key, preset replies)${NC}"
else
  MOCK_MODE="${GREEN}Live LLM mode${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Xplore.ai is ready!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  LLM mode:    ${MOCK_MODE}"
echo ""
echo -e "  API Docs:     ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  ReDoc:        ${CYAN}http://localhost:8000/redoc${NC}"
echo -e "  Prometheus:   ${CYAN}http://localhost:9090${NC}"
echo -e "  Grafana:      ${CYAN}http://localhost:3000${NC} (admin/admin)"
echo -e "  Flower:       ${CYAN}http://localhost:5555${NC}"
echo ""
echo -e "  Demo account: ${CYAN}demo@example.com / demo123456${NC}"
echo ""
echo -e "  Common commands:"
echo -e "    ${CYAN}make help${NC}         List make targets"
echo -e "    ${CYAN}make logs${NC}         Tail API logs"
echo -e "    ${CYAN}make up-full${NC}      Start full stack (Ollama + monitoring)"
echo -e "    ${CYAN}make ollama-pull${NC}  Pull Ollama models"
echo ""
