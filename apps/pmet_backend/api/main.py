from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .routes import tasks, files, results, demo, indexing, admin, admin_stats
from ..config import config

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config.TASKS_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
    pass

app = FastAPI(
    title="PMET API",
    description="Paired Motif Enrichment Tool - Task Submission and Management API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(indexing.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(admin_stats.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "name": "PMET API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
