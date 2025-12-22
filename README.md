# finsight-ai (Cloud Run: single service)

This repo runs **frontend + backend in one Cloud Run service**:
- **Backend**: FastAPI (served on `/api/*`)
- **Frontend**: Vite build served as static files by FastAPI

## Run locally (recommended: two terminals)

### 1) Backend (FastAPI)
From repo root:

```bash
cd backend
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be at:
- http://localhost:8000
- API routes: http://localhost:8000/api

### 2) Frontend (Vite dev server)
From repo root:

```bash
cd frontend
npm ci
npm run dev
```

Frontend will be at:
- http://localhost:5173

Notes:
- The frontend is configured to call the backend using `API_BASE_URL = '/api'`.
- In local dev, you may need a Vite proxy to forward `/api` to `http://localhost:8000` (if you don’t already have one).

## Run locally (single container)

Build and run the Docker image:

```bash
docker build -t finsight-ai .
docker run --rm -p 8080:8080 finsight-ai
```

Open:
- http://localhost:8080

## Deploy to Cloud Run

### 1) Authenticate (if needed)
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

### 2) Deploy
From repo root:

```bash
gcloud run deploy finsight-ai \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

After deploy, Cloud Run will output a service URL. Open it in your browser.
