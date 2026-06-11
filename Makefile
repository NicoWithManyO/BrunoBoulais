.PHONY: help install dev migrate run tailwind shell test lint format clean superuser

PY := .venv/bin/python
PIP := .venv/bin/pip
MANAGE := $(PY) manage.py
PORT ?= 8001

# Premier port libre à partir de $(PORT) (incrémente tant qu'un serveur écoute).
FIND_PORT = $(PY) -c "import socket,sys,itertools; busy=lambda p: socket.socket().connect_ex(('127.0.0.1',p))==0; print(next(p for p in itertools.count(int(sys.argv[1])) if not busy(p)))"
# Sort 0 quand le port écoute (sert à attendre que runserver soit prêt).
PORT_LISTENS = $(PY) -c "import socket,sys; sys.exit(0 if socket.socket().connect_ex(('127.0.0.1',int(sys.argv[1])))==0 else 1)"

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
	@PORT=$$($(FIND_PORT) $(PORT)); \
	 trap 'kill 0' INT TERM EXIT; \
	 $(MANAGE) tailwind start & \
	 ( while ! $(PORT_LISTENS) $$PORT; do sleep 0.2; done; \
	   echo ""; \
	   echo "  Front : http://127.0.0.1:$$PORT/"; \
	   echo "  Back  : http://127.0.0.1:$$PORT/gestion/"; \
	   echo "" ) & \
	 $(MANAGE) runserver $$PORT

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
