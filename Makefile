.PHONY: dev up down test scenarios

dev:
	pip install -e ".[dev]"

up:
	docker compose up -d --build

down:
	docker compose down -v

test:
	pytest -q

scenarios:
	python -m scenarios.run --dir scenarios/cases
