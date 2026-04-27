"""Celery application bootstrap."""

import importlib

from celery import Celery

from app.core.config import settings

TASK_MODULES = (
    "app.tasks.ingestion_tasks",
    "app.tasks.vectorization_tasks",
)

celery_app = Celery(
    "knowledge_base_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=list(TASK_MODULES),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_retry_backoff=True,
    task_retry_backoff_max=600,
)

for module in TASK_MODULES:
    importlib.import_module(module)
