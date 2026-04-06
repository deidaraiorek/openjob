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
        "daily-source-sync": {
            "task": "app.tasks.discovery.sync_all_sources",
            "schedule": 60 * 60 * 24,
        },
    },
)
