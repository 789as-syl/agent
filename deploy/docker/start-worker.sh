#!/bin/sh
set -eu

exec celery -A app.core.celery_app.celery_app worker --loglevel="${CELERY_LOG_LEVEL:-INFO}"

