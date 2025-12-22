# Credit Evaluation Engine - AI Agent Instructions

## System Overview
Full-stack application for extracting transaction data from bank statement PDFs using LandingAI's ADE (Advanced Document Extraction). Dual-environment storage system (GCS for production, local filesystem for dev/testing).

**Tech Stack:** FastAPI backend + React/TypeScript frontend + LandingAI ADE + GCS

## Architecture

### Storage Abstraction Pattern
[app/services/storage.py](../backend/app/services/storage.py) implements pluggable storage backends:
- **Interface:** `StorageBackend` ABC defines all storage operations
- **Implementations:** `GCSBackend` (prod) and `LocalBackend` (dev/test)
- **Selection:** Set `ENVIRONMENT=local` to use local filesystem, otherwise defaults to GCS
- **Structure:** 
  - `uploads/{folder_id}/` - Original uploaded PDFs
  - `parsed/{folder_id}/{filename}.json` - Cached parsed markdown + chunks
  - `processed/{folder_id}/{filename}.csv` - Extracted transaction CSVs
  - `schemas/{folder_id}/{filename}.json` - Custom extraction schemas (per file)
  - `metadata/{folder_id}.json` - Folder metadata

All storage calls go through `StorageService` facade which routes to the active backend.

### Document Processing Pipeline
[app/routers/process.py](../backend/app/routers/process.py) implements a **two-phase cost-optimized workflow**:

**Phase 1: Parse (one-time, expensive)**
- `POST /process/{folder_id}/{filename}/parse` - Parse document to markdown + chunks
- `client.ade.parse()` converts PDF → markdown + chunks
- Result cached to `parsed/{folder_id}/{filename}.json` for reuse
- Set `force_reparse=True` only when parsing model updates

**Phase 2: Extract (repeatable, cheaper)**
- `POST /process/{folder_id}/{filename}/extract` - Extract structured data using schema
- `client.ade.extract()` pulls data from cached markdown
- Uses custom schema if saved, otherwise default `BankStatementFieldExtractionSchema`
- Can re-extract multiple times from same parse → massive cost savings
- Processes chunks individually for long documents (prevents cutoff)

**Legacy Endpoint (backward compatible):**
- `POST /process/{folder_id}/{filename}` - Parse + Extract in one call (original workflow)

### Custom Schema Workflow
Users can customize what data is extracted without re-parsing:

1. **Parse once:** `POST /parse` generates markdown + chunks (cached)
2. **Get schema:** `GET /schema` returns current schema (custom or default)
3. **Edit schema:** `PUT /schema` saves custom extraction schema
4. **Extract:** `POST /extract` uses custom schema → generates CSV
5. **Iterate:** Modify schema and re-extract without re-parsing

Schemas are stored per-file at `schemas/{folder_id}/{filename}.json`.

### Transaction Normalization
The `Transaction` Pydantic model ([process.py:62-252](../backend/app/routers/process.py#L62-L252)) handles polymorphic bank statement layouts:
- **Separate columns:** `credit_amount` + `debit_amount` → signed output
- **Single amount:** `raw_amount` with sign detection (parentheses, minus, "Dr")
- **Type indicator:** `type_indicator` ("Dr"/"Cr") determines sign

`@model_validator` `normalize_transaction_amount()` consolidates all formats into signed `amount` field ("+100.00" or "-50.00").

## Development Workflows

### Backend Setup & Testing
```bash
cd backend/
pip install -e ".[test]"              # Install with test dependencies
./run_tests.sh                         # Runs pytest with coverage
pytest tests/test_process.py -v       # Run specific test file
ENVIRONMENT=local pytest tests/        # Force local storage backend
```

**Test Fixtures:** [tests/conftest.py](../backend/tests/conftest.py)
- `local_storage_service` - Auto-configures local backend, tracks test folders for cleanup
- `client` - FastAPI TestClient for integration tests
- Tests use actual `local_storage/` directory (not temp) for realistic behavior

### Frontend Development
```bash
cd frontend/
npm run dev                           # Vite dev server (port 5173)
npm run build                         # Production build
```

**API Configuration:** [constants.ts](../frontend/constants.ts) sets `API_BASE_URL=http://localhost:8000`

### Running Full Stack
```bash
# Terminal 1 - Backend
cd backend/ && uvicorn main:app --reload

# Terminal 2 - Frontend  
cd frontend/ && npm run dev
```

## Critical Environment Variables

### Backend ([.env.example](../backend/.env.example))
- `ENVIRONMENT=local` → Uses local filesystem (dev/test)
- `GCS_BUCKET_NAME` → Required for GCS backend (production)
- `ADE_API_KEY` or `VISION_AGENT_API_KEY` → LandingAI credentials (both supported)

### Frontend
- `API_BASE_URL` in [constants.ts](../frontend/constants.ts) must match backend host

## Project-Specific Patterns

### Router Organization
- [app/routers/folders.py](../backend/app/routers/folders.py) - CRUD for folders + file upload/download
- [app/routers/process.py](../backend/app/routers/process.py) - Document processing endpoints:
  - Parse: `/parse` - Convert PDF to markdown/chunks
  - Schema: `/schema` (GET/PUT/DELETE) - Manage custom extraction schemas
  - Extract: `/extract` - Extract data using stored schema
  - Legacy: `POST /{filename}` - Combined parse + extract
  - Metadata: `/metadata`, `/markdown` - View parsed document data
  - Download: `/download` - Get processed CSV

Both import from centralized `app.services.storage.StorageService`.

### Error Handling
- FastAPI raises `HTTPException` with status codes
- Frontend [lib/api.ts](../frontend/lib/api.ts) has axios interceptor for structured error handling
- Storage backends print errors but don't crash (e.g., GCS connection failures log warnings)

### File Naming Convention
- Uploaded files: Keep original names in `uploads/{folder_id}/`
- Processed outputs: `{original_filename}.csv` in `processed/{folder_id}/`
- Cached parses: `{original_filename}.json` in `parsed/{folder_id}/`
- Custom schemas: `{original_filename}.json` in `schemas/{folder_id}/`

### Testing Best Practices
- Use `monkeypatch.setenv("ENVIRONMENT", "local")` to force local storage
- Fixtures track folder IDs via `_test_folder_ids` set for bulk cleanup
- Tests run against actual `local_storage/` for integration validation
- Use `cleanup_test_folders.py` to clean orphaned test data

## Key Dependencies
- **ade-python** (0.2.0+) - Official LandingAI SDK with retry/timeout handling
- **FastAPI** - Backend framework with auto-generated OpenAPI docs at `/docs`
- **Pydantic v2** - Schema validation with `@field_validator` and `@model_validator`
- **Google Cloud Storage** - Production blob storage
- **React Router v7** - Frontend routing ([App.tsx](../frontend/App.tsx))

## When Adding Features

**New storage operations:** Add to `StorageBackend` interface, implement in both `GCSBackend` and `LocalBackend`

**New extraction fields:** Update `Transaction` model and add normalization logic in validators

**New routers:** Register in [main.py](../backend/main.py) via `app.include_router()`

**API changes:** Update [frontend/lib/api.ts](../frontend/lib/api.ts) and TypeScript types in [types.ts](../frontend/types.ts)
