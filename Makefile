.PHONY: setup check test anubis backend qdrant sync compose-up compose-down

setup:
	./scripts/setup.sh

check:
	./scripts/check.sh

test:
	.venv/bin/python -m unittest discover -s tests -p 'test*.py'

anubis:
	.venv/bin/anubis

backend:
	.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

qdrant:
	docker compose up -d qdrant

sync:
	.venv/bin/anubis --sync

compose-up:
	docker compose up -d

compose-down:
	docker compose down
