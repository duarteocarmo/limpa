#!/bin/sh
set -eux

echo "Setup database directory..."
mkdir -p "db"

echo "Collect static files..."
uv run python manage.py collectstatic --noinput

echo "Migrate database..."
uv run python manage.py migrate --noinput

echo "Start gunicorn..."
exec uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000
