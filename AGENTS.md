# Copilot Agents Playbook — FinSight AI

## Quick Commands (runnable)

Prereqs:
- Python 3.10+ (prefer uv; ask first if using system Python/pyenv)
- uv (Ask first if not installed)
- Node.js 18+ (Ask first if different)
- Optional: Google Cloud SDK for GCS (production)

Backend (FastAPI):
- Run (dev):
  - cd backend
  - ENVIRONMENT=local uv run uvicorn main:app --reload
- Run (serve built frontend too):
  - cd frontend && npm run build
  - cd ../backend
  - uv run uvicorn main:app --reload
  - Note: backend/main.py mounts frontend/dist at "/"

Frontend (React + Vite + TypeScript):
- Setup:
  - cd frontend
  - npm install
- Dev:
  - npm run dev
- Build:
  - npm run build

Tests:
- Backend tests (local storage):
  - cd backend
  - ENVIRONMENT=local uv run pytest tests/ -v
- Single test file:
  - ENVIRONMENT=local uv run pytest tests/test_process.py -v
- Note: tests use FastAPI TestClient and local_storage via fixtures.

Lint/Format:
- Python (Ask first whether these tools are standard here):
  - cd backend && uv run ruff check .
  - Optional: cd backend && uv run ruff format .  # auto-fix (ask first)
  - Note: Black is not installed by default here; use only if the project adds it. Prefer Ruff for lint/format.
- TypeScript (Ask first; depends on project config):
  - npx eslint "frontend/**/*.{ts,tsx}"
  - npx prettier --check "frontend/**/*.{ts,tsx,css,md}"
  - npx prettier --write "frontend/**/*.{ts,tsx,css,md}"  # if fixing

Typecheck (TS):
- cd frontend
- Typecheck app sources:
  - npx tsc --noEmit -p tsconfig.json
- Typecheck Vite/Node config:
  - npx tsc --noEmit -p tsconfig.node.json
- If you see TS6305 about composite builds, run once to satisfy project references:
  - npx tsc -b
  - Note: with jsx="react-jsx" and strict unused checks, remove legacy `import React` lines to silence TS6133.

## Project Knowledge

- Backend: FastAPI, Pydantic v2, Uvicorn, Google Cloud Storage client
- Frontend: React + TypeScript, Vite, Axios, React Router
- ADE client (LandingAI) used via app/services, cost-optimized parse→extract workflow

Key directories and runtime behaviors remain as documented above.

Environment variables:
- Backend: ENVIRONMENT, GCS_BUCKET_NAME, VISION_AGENT_API_KEY (ADE credentials also supported as ADE_API_KEY; Ask first which is active)
- Frontend: API_BASE_URL defaults to "/api" (same-origin)

## Global Boundaries (for Copilot agents)

- Always:
  - Keep parse→extract as two-phase; cache parsed output to avoid re-parsing.
  - Implement storage changes in both Local and GCS backends.
  - Update TypeScript types and frontend api.ts when backend API changes.

- Ask first:
  - Introducing new env vars or changing existing ones.
  - Adding third-party deps or changing ADE integration details.
  - Creating new routes or altering URL structure.

- Never:
  - Commit secrets or credentials.
  - Break StorageBackend interface without migration plan.
  - Ship code that depends on external services in tests.