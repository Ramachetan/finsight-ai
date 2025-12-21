# Credit Evaluation Engine - AI Coding Instructions

## Project Overview
A FastAPI backend service that processes bank statements from Google Cloud Storage (GCS) and extracts transaction data using LandingAI's vision model. The system organizes statements into logical folders and uses LandingAI ADE for structured data extraction.

## Architecture

### Core Structure
- **`app/routers/`**: HTTP endpoint handlers
  - `folders.py`: Folder/workspace management (CRUD operations)
  - `process.py`: Bank statement processing via LandingAI ADE
- **`app/services/storage.py`**: GCS abstraction layer for all cloud operations
- **`app/models/schemas.py`**: Pydantic models for request/response validation

### Data Flow
1. **Upload Phase**: Users create folders and upload PDFs via `POST /folders/{folder_id}/upload`
2. **Processing Phase**: `POST /process/{folder_id}/{filename}` triggers:
   - File retrieval from GCS
   - LandingAI parsing (dpt-2 model) → markdown extraction
   - Schema-based extraction using `BankStatementFieldExtractionSchema`
   - CSV conversion and storage back to GCS
3. **Storage Layout** (GCS):
   - `metadata/{folder_id}`: Folder metadata blobs with name and status
   - `uploads/{folder_id}/{filename}`: Original PDF files
   - `processed/{folder_id}/{filename}`: Extracted CSV results

## Key Patterns & Conventions

### GCS Integration (StorageService)
- Single `StorageService` instance per router - initialized at module level
- **Folder Metadata**: Folders are logical constructs tracked via GCS metadata blobs, not actual directories
- **Status Tracking**: Metadata tracks `"status": "EMPTY"` or `"HAS_FILES"` for folders
- **Error Handling**: All methods return `None`/empty list on GCS connection failure; production deployments require proper error handling
- GCS paths use forward slashes and follow pattern: `{category}/{folder_id}/{filename}`

**Example Pattern** (from storage.py):
```python
blob = self.bucket.blob(f"metadata/{folder_id}")
metadata = {"original_name": folder_name, "status": "EMPTY"}
blob.metadata = metadata
blob.patch()  # Must patch to persist metadata changes
```

### Pydantic Schema-Based Data Extraction
The `BankStatementFieldExtractionSchema` defines structured extraction for bank statements with nested models:
- `AccountInfo`: Account details (IFSC, account number, branch address)
- `CustomerInfo`: Customer residence details
- `Transaction[]`: Individual transaction records with date, amount, balance, remarks
- `StatementInfo`: Statement period metadata

LandingAI response handling requires flexible conversion due to varying response types:
```python
def get_data_dict(obj):
    if isinstance(obj, dict): return obj
    if hasattr(obj, "model_dump"): return obj.model_dump()
    if hasattr(obj, "dict"): return obj.dict()
```

### LandingAI ADE Workflow
1. Initialize client with `VISION_AGENT_API_KEY` from `.env`
2. Parse document: `client.parse(document=Path(...), model="dpt-2")`
3. Extract structured data: `client.extract(schema=json_schema, markdown=BytesIO(...))`
4. Response may be wrapped in `"extraction"` key - check and unwrap before instantiation

## Development Workflows

### Local Setup
```bash
# Install dependencies (Python 3.12+)
pip install -e .

# Set environment (see .env template)
export GCS_BUCKET_NAME=your-bucket
export VISION_AGENT_API_KEY=your-api-key
export GOOGLE_CLOUD_PROJECT=your-project-id

# Run development server
uvicorn main:app --reload
```

### Testing GCS Operations
- Ensure `GOOGLE_CLOUD_APPLICATION_CREDENTIALS` is set for authentication
- Use `StorageService()` directly in tests to avoid router dependencies
- Folder metadata is persisted on blob.patch() - verify with GCS Console

### Adding New API Endpoints
1. Create router in `app/routers/`
2. Import and register in `main.py`: `app.include_router()`
3. Use `StorageService()` singleton for GCS operations
4. Define request/response models in `app/models/schemas.py`

## External Dependencies & Integration Points

### Google Cloud Storage
- **Client**: `google.cloud.storage.Client()` auto-discovers credentials from environment
- **Bucket Name**: Loaded from `GCS_BUCKET_NAME` env var (defaults to "credit-eval-engine-uploads")
- **Operations**: All I/O goes through `StorageService` singleton to maintain connection state

### LandingAI Document Parsing
- **API Key**: Required in `VISION_AGENT_API_KEY`
- **Model**: Currently hardcoded to `"dpt-2"` for document parsing
- **Output**: Markdown format that requires schema-based extraction
- **Dependency**: `landingai-ade>=0.1.0` package provides client and schema utilities

### Environment Variables (.env)
- `GCS_BUCKET_NAME`: Target bucket (required, defaults in StorageService)
- `VISION_AGENT_API_KEY`: LandingAI API authentication
- `GOOGLE_CLOUD_PROJECT`: GCP project ID (used by google-cloud-storage)
- `GOOGLE_CLOUD_LOCATION`: Region hint (default: "global")

## Project-Specific Quirks

- **Metadata Persistence**: GCS blob metadata requires explicit `.patch()` call - `.upload_from_string()` alone doesn't guarantee metadata is saved
- **Response Unwrapping**: LandingAI extract responses may wrap extraction data in `"extraction"` key - always check before schema instantiation
- **Folder as Abstraction**: Folders don't create actual GCS directories; they're logical groupings tracked via metadata blobs in `metadata/` prefix
- **CSV Output Format**: Fixed columns: `["Date", "Transaction ID", "Description", "Amount", "Balance"]` - defined in `convert_extraction_to_csv()`
- **Status Enum**: Only two known statuses: `"EMPTY"` (no files) and `"HAS_FILES"` (files present)
