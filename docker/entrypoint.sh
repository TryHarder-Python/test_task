#!/bin/sh
set -eu

# Bring the schema up to date before serving, so the code never runs against an old schema.
alembic upgrade head

exec "$@"
