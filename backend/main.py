from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import folders, process

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
app.include_router(folders.router)
app.include_router(process.router)
