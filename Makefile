default: help

.PHONY: help
help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

.PHONY: install
install: # Install dependencies with uv
	uv sync

.PHONY: format
format: # Format the codebase with ruff
	uv run ruff check . --fix 
	uv run ruff format .

.PHONY: check 
check: # Run linting and check
	uv lock --check
	uv run ruff check . 
	uv run ruff format --check .
	uv run ty check .
	uv run deptry .

.PHONY: lint
lint: check

.PHONY: clean 
clean: # Clean up temporary files
	@rm -rf .ipynb_checkpoints
	@rm -rf **/.ipynb_checkpoints
	@rm -rf .pytest_cache
	@rm -rf **/.pytest_cache
	@rm -rf __pycache__
	@rm -rf **/__pycache__
	@rm -rf build
	@rm -rf dist

WEBSERVER_PORT := 8000

.PHONY: run
run: # Run migrations, start server and worker
	-lsof -ti:$(WEBSERVER_PORT) | xargs kill -9 2>/dev/null || true
	uv run python manage.py migrate
	uv run python manage.py runserver $(WEBSERVER_PORT) & uv run python manage.py db_worker & wait

.PHONY: worker
worker: # Run the background task worker
	uv run python manage.py db_worker

.PHONY: docker
docker: # Run docker compose with env vars
	docker compose --env-file .env up --build --force-recreate

.PHONY: refresh
refresh: # Refresh all podcast feeds
	uv run python manage.py refresh_feeds

