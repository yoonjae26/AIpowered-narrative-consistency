"""NarrativeOS Backend - Main Application Entry Point."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.middleware.auth_middleware import AuthMiddleware
from backend.api.middleware.logging_middleware import LoggingMiddleware
from backend.api.middleware.rate_limiter import RateLimiterMiddleware
from backend.api.routes.auth import router as auth_router
from backend.api.routes.consistency import router as consistency_router
from backend.api.routes.documents import router as documents_router
from backend.api.routes.export import router as export_router
from backend.api.routes.narrative import router as narrative_router
from backend.api.routes.projects import router as projects_router
from backend.api.routes.ws import router as ws_router
from backend.core.config import get_settings
from backend.core.exceptions import NarrativeError
from backend.llm.healthcheck import run_startup_llm_healthcheck


settings = get_settings()

app = FastAPI(title=settings.app_name, description="AI-powered narrative writing and consistency management system", version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(LoggingMiddleware)


@app.on_event("startup")
async def startup_health_checks() -> None:
    app.state.llm_health = run_startup_llm_healthcheck()


@app.exception_handler(NarrativeError)
async def narrative_error_handler(_: Request, exc: NarrativeError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": exc.message, "details": exc.details})


app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(documents_router)
app.include_router(narrative_router)
app.include_router(consistency_router)
app.include_router(export_router)
app.include_router(ws_router)


@app.get("/")
async def root() -> dict[str, object]:
    return {"message": "Welcome to NarrativeOS API", "version": settings.app_version, "status": "operational"}


@app.get("/health")
async def health_check() -> dict[str, object]:
    llm_health = getattr(app.state, "llm_health", None)
    return {"status": "healthy", "llm": llm_health}


@app.get("/meta")
async def meta() -> dict[str, object]:
    return {"name": settings.app_name, "version": settings.app_version, "environment": settings.environment}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
