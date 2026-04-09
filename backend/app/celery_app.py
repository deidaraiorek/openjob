from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "openjob",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.applications",
        "app.tasks.discovery",
        "app.tasks.job_relevance",
        "app.tasks.linkedin",
        "app.tasks.role_profile_expansion",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    beat_schedule={
        "enqueue-due-source-syncs": {
            "task": "app.tasks.discovery.enqueue_due_source_syncs",
            "schedule": settings.source_sync_poll_interval_seconds,
        },
    },
)
