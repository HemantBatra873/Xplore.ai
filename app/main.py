from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.middleware import RequestIDMiddleware
import app.models.knowledge_base  # noqa: F401 — register knowledge base models with SQLAlchemy metadata
import app.models.workspace  # noqa: F401 — register workspace models with SQLAlchemy metadata
from app.api.routers import auth, chat, health, knowledge, observability, rag, tasks, users, worker, workspaces
from app.core.config import settings
from app.core.logging import logger
from app.db.base import Base
from app.db.session import engine
from app.utils.errors import AppException, app_exception_handler, http_exception_handler


def _validate_startup_config():
    errors = []

    if settings.SECRET_KEY == "replace_with_a_long_random_secret_key":
        errors.append("SECRET_KEY is still the default value. Set a strong random key in .env.")

    if not settings.LLM_API_KEY:
        logger.warning(
            "LLM_API_KEY is not set. LLM features will rely on per-user BYOK configs only."
        )

    if errors:
        for err in errors:
            logger.error(f"Config validation error: {err}")
        raise RuntimeError("Startup config validation failed. Fix the errors above and restart.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")

    _validate_startup_config()

    # Database connectivity check
    logger.info("Testing database connection...")
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            logger.info(f"Database connection successful! (Test query returned: {result.scalar()})")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")

    # pgvector extension check (required for RAG)
    logger.info("Checking pgvector extension...")
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
            if row:
                logger.info("pgvector extension is installed.")
            else:
                logger.warning(
                    "pgvector extension is NOT installed. RAG features (vector search) will not work. "
                    "Run: CREATE EXTENSION vector;"
                )
    except Exception as e:
        logger.warning(f"pgvector extension check failed (non-fatal): {e}")

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured.")

    # Redis connectivity check
    logger.info("Testing Redis connection...")
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await redis_client.ping()
        logger.info("Redis connection successful!")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Rate limiting and task queue will not work.")
    finally:
        await redis_client.aclose()

    yield

    logger.info("Shutting down FastAPI application...")


app = FastAPI(
    title="Xplore.ai",
    description="Xplore.ai AI workspace foundation.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None,
)

# Register middleware
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize and expose Prometheus metrics
Instrumentator().instrument(app).expose(app)


# Custom Swagger UI with dark-mode CSS
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    html_content = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
    ).body.decode("utf-8")

    # Inject CSS so Swagger UI works in dark mode while keeping light mode
    custom_css = """
    <style>
        @media (prefers-color-scheme: dark) {
            body { background-color: #121212 !important; color: #e0e0e0 !important; }
            
            /* Top bar and base layout */
            .swagger-ui .topbar { background-color: #1e1e1e !important; border-bottom: 1px solid #333; }
            .swagger-ui .info .title, .swagger-ui .info p, .swagger-ui .info li { color: #e0e0e0 !important; }
            .swagger-ui .scheme-container { background-color: #1e1e1e !important; border-bottom: 1px solid #333; box-shadow: none; }
            
            /* Operation blocks */
            .swagger-ui .opblock { border-color: #333 !important; background-color: rgba(255,255,255,0.02); }
            .swagger-ui .opblock-summary-control { outline: none; }
            .swagger-ui .opblock .opblock-summary-operation-id, 
            .swagger-ui .opblock .opblock-summary-path, 
            .swagger-ui .opblock .opblock-summary-path__deprecated { color: #e0e0e0 !important; }
            .swagger-ui .opblock-description-wrapper p { color: #b0b0b0 !important; }
            
            /* Modal and auth UI */
            .swagger-ui .dialog-ux .modal-ux { background-color: #1e1e1e !important; border: 1px solid #444 !important; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            .swagger-ui .dialog-ux .modal-ux-header { border-bottom: 1px solid #444 !important; }
            .swagger-ui .dialog-ux .modal-ux-header h3, 
            .swagger-ui .dialog-ux .modal-ux-content h4, 
            .swagger-ui .dialog-ux .modal-ux-content p { color: #e0e0e0 !important; }
            .swagger-ui .auth-container { border-bottom-color: #444 !important; }
            
            /* Form controls */
            .swagger-ui input[type=text], .swagger-ui input[type=password], .swagger-ui textarea, .swagger-ui select {
                background-color: #2d2d2d !important;
                color: #fff !important;
                border: 1px solid #555 !important;
            }
            .swagger-ui input[type=text]:focus, .swagger-ui input[type=password]:focus, .swagger-ui textarea:focus {
                border-color: #49cc90 !important;
            }
            
            /* Buttons */
            .swagger-ui .btn { color: #e0e0e0; border-color: #666; background: transparent; }
            .swagger-ui .btn.authorize { color: #49cc90 !important; border-color: #49cc90 !important; }
            .swagger-ui .btn.execute { background-color: #49cc90 !important; color: #fff !important; border-color: #49cc90 !important; }
            .swagger-ui .btn.cancel { border-color: #f93e3e !important; color: #f93e3e !important; }
            .swagger-ui .btn-done { color: #fff !important; }
            
            /* Tables and parameters */
            .swagger-ui table thead tr td, .swagger-ui table thead tr th { border-bottom-color: #444 !important; color: #e0e0e0 !important; }
            .swagger-ui .parameter__name, .swagger-ui .parameter__type { color: #e0e0e0 !important; }
            .swagger-ui .response-col_status, .swagger-ui .response-col_description { color: #e0e0e0 !important; }
            .swagger-ui table.model tbody tr td { border-bottom-color: #333 !important; }
            
            /* Response highlight blocks */
            .swagger-ui .highlight-code { background-color: #2d2d2d !important; }
            .swagger-ui .model-box { background-color: #2d2d2d !important; }
            .swagger-ui .model { color: #e0e0e0 !important; }
            .swagger-ui .prop-type { color: #8aafff !important; }
            
            /* Auth error text visibility in dark mode */
            .swagger-ui .auth-container .errors { background-color: #401010 !important; color: #ff6060 !important; }
            .swagger-ui .dialog-ux .modal-ux-header .close-modal { fill: #e0e0e0 !important; }
            .swagger-ui svg { fill: #e0e0e0; }
            .swagger-ui .btn.authorize svg { fill: #49cc90 !important; }
        }
    </style>
    """
    html_content = html_content.replace("</head>", f"{custom_css}</head>")
    return HTMLResponse(html_content)


# Register global exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# Register API routers
app.include_router(health.router, prefix="/api/v1/health", tags=["Health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
app.include_router(workspaces.router, prefix="/api/v1/workspaces", tags=["Workspaces"])
app.include_router(worker.router, prefix="/api/v1/worker", tags=["Worker (Async)"])
app.include_router(rag.router, prefix="/api/v1/rag", tags=["RAG"])
app.include_router(knowledge.router, prefix="/api/v1/knowledge-bases", tags=["Knowledge"])
app.include_router(observability.router, prefix="/api/v1/observability", tags=["Observability"])


# Mount frontend static files
# Prefer app/static/ (Docker build) then frontend/dist/ (local dev)
import os

_static_candidates = [
    os.path.join(os.path.dirname(__file__), "static"),  # Docker image: app/static/
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"),  # Dev: frontend/dist/
]
_static_dir = None
for _dir in _static_candidates:
    if os.path.exists(_dir) and os.listdir(_dir):
        _static_dir = _dir
        break

if _static_dir:
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
else:
    # JSON welcome when no frontend build is present
    @app.get("/", summary="Root welcome", tags=["Root"])
    async def root():
        return {
            "message": "Welcome to Xplore.ai. Visit /docs for API documentation.",
            "docs_url": "/docs",
        }
