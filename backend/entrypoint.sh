#!/bin/sh
set -e
# Schema changes run once in the compose `migrate` service.
# Set RUN_MIGRATIONS=1 only for that one-shot job.
if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
  alembic upgrade head
fi
exec "$@"
