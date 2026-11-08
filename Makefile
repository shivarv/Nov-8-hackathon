.PHONY: up down reset logs test test-backend test-frontend lint

up:            ## Build and start db, backend, frontend
	docker compose up --build

down:          ## Stop containers
	docker compose down

reset:         ## Stop and wipe the database volume (re-seeds on next `make up`)
	docker compose down -v

logs:
	docker compose logs -f backend

test: test-backend test-frontend

test-backend:
	docker compose run --rm backend sh -c "pip install -q -r requirements-dev.txt && pytest -q"

test-frontend:
	docker compose run --rm frontend npm run build

lint:
	docker compose run --rm backend sh -c "pip install -q -r requirements-dev.txt && ruff check ."
