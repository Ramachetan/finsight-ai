from pathlib import Path

from app.routers import folders, process
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Credit Evaluation Engine",
    description="API for processing bank statements and extracting transaction data",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Include routers
app.include_router(folders.router, prefix="/api")
app.include_router(process.router, prefix="/api")

# Serve static files (built React app)
# API routes are mounted above; below we serve the built SPA.
static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        SPA fallback: serve index.html for client-side routes (e.g. /folder/:id).
        If the requested path matches a real file in dist (favicon, etc.), serve it.
        """
        requested_path = static_dir / full_path
        if requested_path.exists() and requested_path.is_file():
            return FileResponse(str(requested_path))

        return FileResponse(str(static_dir / "index.html"))
