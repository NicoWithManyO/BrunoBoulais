.PHONY: help install dev migrate run tailwind shell test lint format clean superuser

PY := .venv/bin/python
PIP := .venv/bin/pip
MANAGE := $(PY) manage.py
PORT ?= 8001

help:
	@echo "Cibles disponibles :"
	@echo "  install     Installe les dépendances (dev)"
	@echo "  migrate     Applique les migrations"
	@echo "  run         Lance le serveur de dev"
	@echo "  tailwind    Lance tailwind en watch"
	@echo "  dev         Lance Django + Tailwind en parallèle"
	@echo "  shell       Ouvre un shell Django"
	@echo "  superuser   Crée un super-utilisateur"
	@echo "  test        Lance pytest"
	@echo "  lint        Lance ruff"
	@echo "  format      Formate le code (ruff format)"

install:
	$(PIP) install -r requirements/dev.txt

migrate:
	$(MANAGE) migrate

run:
	$(MANAGE) runserver $(PORT)

tailwind:
	$(MANAGE) tailwind start

dev:
	@trap 'kill 0' INT TERM EXIT; \
	 $(MANAGE) tailwind start & \
	 $(MANAGE) runserver $(PORT); \
	 wait

shell:
	$(MANAGE) shell

superuser:
	$(MANAGE) createsuperuser

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

format:
	.venv/bin/ruff format .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
