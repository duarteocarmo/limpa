#!/bin/sh
set -eux

echo "Setup database directory..."
mkdir -p "db"

echo "Collect static files..."
uv run --no-sync python manage.py collectstatic --noinput

echo "Migrate database..."
uv run --no-sync python manage.py migrate --noinput

echo "Create superuser if not exists..."
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
    uv run --no-sync python manage.py createsuperuser --noinput || true
fi

echo "Start gunicorn..."
exec uv run --no-sync gunicorn config.wsgi:application --bind 0.0.0.0:4444 --access-logfile -
