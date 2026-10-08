HOST ?= cpbox
DIR ?= /opt/antoncopilot

.PHONY: check sync build deploy logs

check:
	uv run ruff check src tests
	uv run mypy
	uv run pytest -q

sync:
	rsync -az --delete --exclude-from=.dockerignore --exclude=.env ./ $(HOST):$(DIR)/

build: sync
	ssh $(HOST) 'cd $(DIR) && docker compose build'

deploy: build
	ssh $(HOST) 'cd $(DIR) && docker compose up -d'

logs:
	ssh $(HOST) 'cd $(DIR) && docker compose logs -f --tail 100 bot'
