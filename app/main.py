import nest_asyncio
nest_asyncio.apply()


from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router
from app.api.channels import router as channels_router
import uvicorn
from app.core.logger import setup_logging
from app.core.config import CORS_ORIGINS, validate_production_config
from loguru import logger
import time
from prometheus_fastapi_instrumentator import Instrumentator

# Setup structured logging
setup_logging()


# ──────────────────────────────────────────────
# FastAPI Lifespan — Startup/Shutdown hooks
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: validate config, start observability."""
    # Startup
    validate_production_config()

    # Initialize Phoenix Tracing & LLM Observability (lazy, not at import time)
    try:
        import phoenix as px
        from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
        px.launch_app()
        LlamaIndexInstrumentor().instrument()
        logger.info("Phoenix observability initialized")
    except Exception as e:
        logger.warning("Phoenix init skipped: %s", e)

    logger.info("Enterprise RAG Agent v3.0 started")
    yield
    # Shutdown
    logger.info("Enterprise RAG Agent shutting down")


app = FastAPI(title="Enterprise-RAG-Agent API", lifespan=lifespan)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")
    return response

# Initialize Prometheus Instrumentator
Instrumentator().instrument(app).expose(app, include_in_schema=False, should_gzip=True)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")
app.include_router(channels_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to Enterprise-RAG-Agent API"}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Enterprise-RAG-Agent", "version": "3.0"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
