.PHONY: setup check test backend desktop qdrant compose-up compose-down

setup:
	./scripts/setup.sh

check:
	./scripts/check.sh

test:
	.venv/bin/python -m unittest discover -s tests -p 'test*.py'

backend:
	.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

desktop:
	cd desktop && npm run tauri dev

qdrant:
	docker compose up -d qdrant

compose-up:
	docker compose up -d

compose-down:
	docker compose down
