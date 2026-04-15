import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.config import get_settings
import app.db.models  # noqa: F401
from app.domains.application_accounts.routes import router as application_accounts_router
from app.domains.answers.routes import router as answers_router
from app.domains.applications.routes import router as applications_router
from app.domains.jobs.routes import router as jobs_router
from app.domains.questions.routes import router as questions_router
from app.domains.role_profiles.routes import router as role_profile_router
from app.domains.sources.routes import router as sources_router
from app.db.base import Base
from app.db.session import get_engine
from app.tasks.job_relevance import drain_all_relevance_tasks


def ensure_database_ready() -> None:
    settings = get_settings()
    engine = get_engine(settings.database_url)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {
        "accounts",
        "application_accounts",
        "job_sources",
        "jobs",
        "job_sightings",
        "apply_targets",
        "job_relevance_evaluations",
        "job_relevance_tasks",
    }

    if required_tables.issubset(existing_tables):
        return

    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
        return

    missing_tables = ", ".join(sorted(required_tables - existing_tables))
    raise RuntimeError(
        f"Database is missing required tables: {missing_tables}. Run migrations before starting the API."
    )


def create_app() -> FastAPI:
    settings = get_settings()
    ensure_database_ready()

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(sources_router, prefix="/api")
    app.include_router(role_profile_router, prefix="/api")
    app.include_router(application_accounts_router, prefix="/api")
    app.include_router(answers_router, prefix="/api")
    app.include_router(questions_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(applications_router, prefix="/api")

    @app.on_event("startup")
    def _resume_pending_relevance() -> None:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return
        threading.Thread(target=drain_all_relevance_tasks, daemon=True).start()

    return app


app = create_app()
