.PHONY: run test compile docker-build

run:
	python3 bootstrap.py

compile:
	PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q src tests bootstrap.py agents core tools

test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 scripts/run_tests.py

docker-build:
	docker build -t anubis:local .
