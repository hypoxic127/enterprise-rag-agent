import nest_asyncio
nest_asyncio.apply()

import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router
import uvicorn
from app.core.logger import setup_logging
from loguru import logger
import time
from prometheus_fastapi_instrumentator import Instrumentator
import phoenix as px
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

# Setup structured logging
setup_logging()

# Initialize Phoenix Tracing & LLM Observability
px.launch_app()
LlamaIndexInstrumentor().instrument()

app = FastAPI(title="Enterprise-RAG-Agent API")

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

# CORS: defaults to localhost:3000 for dev; set CORS_ORIGINS env var for production
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to Enterprise-RAG-Agent API"}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Enterprise-RAG-Agent"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
