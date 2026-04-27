"""异步任务模块：celery_app。"""

from app.core.celery_app import celery_app


def check_celery_broker() -> bool:
    """Check broker connectivity through the shared Celery app."""
    try:
        inspector = celery_app.control.inspect()
        inspector.stats()
        return True
    except Exception:
        return False
