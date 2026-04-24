from celery import Celery

from .config import get_settings

settings = get_settings()

celery_app = Celery(
    "nexus_api",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["nexus_api.tasks.acp_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
