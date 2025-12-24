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

### 1) Authenticate and Set Project
```bash
gcloud auth login
gcloud config set project project-11da9e7d-fd34-4578-870
```

### 2) Configure Docker for Artifact Registry
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
```

### 3) Build Docker Image for Cloud Run (linux/amd64)
From repo root:

```bash
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/project-11da9e7d-fd34-4578-870/cloud-run-source-deploy/finsight-ai:latest .
```

**Note:** The `--platform linux/amd64` flag is required when building on ARM-based Macs to ensure compatibility with Cloud Run.

### 4) Push Image to Artifact Registry
```bash
docker push us-central1-docker.pkg.dev/project-11da9e7d-fd34-4578-870/cloud-run-source-deploy/finsight-ai:latest
```

### 5) Deploy to Cloud Run
```bash
gcloud run deploy finsight-ai \
  --image us-central1-docker.pkg.dev/project-11da9e7d-fd34-4578-870/cloud-run-source-deploy/finsight-ai:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

After deploy, Cloud Run will output a service URL:
- **Current URL:** https://finsight-ai-1036646057438.us-central1.run.app

### Quick Redeploy (all steps combined)
```bash
# Set project
gcloud config set project project-11da9e7d-fd34-4578-870

# Build, push, and deploy
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/project-11da9e7d-fd34-4578-870/cloud-run-source-deploy/finsight-ai:latest . && \
docker push us-central1-docker.pkg.dev/project-11da9e7d-fd34-4578-870/cloud-run-source-deploy/finsight-ai:latest && \
gcloud run deploy finsight-ai \
  --image us-central1-docker.pkg.dev/project-11da9e7d-fd34-4578-870/cloud-run-source-deploy/finsight-ai:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```
