# Xplore.ai Frontend

The Xplore.ai frontend is a React 19 and TypeScript single-page application built with Vite.

## Features

- Authentication and first-run setup
- Streaming AI chat
- Knowledge-base document management and RAG queries
- Task management
- LLM observability dashboard
- Provider and password settings
- Dependency health view
- Offline mock mode

## Development

```bash
npm install
npm run dev
```

The development server uses `/api/v1` for backend requests. Set `VITE_USE_MOCK=true` to run the UI without a backend.

## Validation

```bash
npm run build
npm run lint
```

## Structure

- `src/pages`: route-level views
- `src/components`: reusable UI and feature components
- `src/services`: API clients
- `src/contexts`: authentication and theme state
- `src/hooks`: streaming and reusable behavior
- `src/mock`: offline API responses
- `src/types`: shared TypeScript contracts
