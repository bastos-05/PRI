COMPOSE ?= docker compose
PYTHON ?= python3
DATA ?= data/final.jsonl
ROWS ?= 10

.DEFAULT_GOAL := help

.PHONY: help build up run start stop down ps logs solr solr-up solr-schema solr-load solr-queries solr-stop

help:
	@printf '%s\n' \
	  'make up            Build and start the Compose stack' \
	  'make build         Build the Airflow image' \
	  'make stop          Stop the stack, preserving containers and data' \
	  'make down          Remove stack containers, preserving named volumes' \
	  'make ps            Show service status' \
	  'make logs          Follow the last 100 log lines from each service' \
	  'make solr          Start Solr, apply the schema and load the corpus' \
	  'make solr-up       Start only Solr and wait until healthy' \
	  'make solr-schema   Start Solr and apply the full schema' \
	  'make solr-load     Start Solr, apply the schema and load DATA' \
	  'make solr-queries  Start Solr and run example queries (ROWS=10)' \
	  'make solr-stop     Stop only Solr, preserving its index' \

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up -d --build

stop:
	$(COMPOSE) stop

down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs --tail=100 -f

solr: solr-load

solr-clear:
	$(PYTHON) solr/load_documents.py --clear

solr-up:
	$(COMPOSE) up -d --wait --wait-timeout 180 solr

solr-schema: solr-up
	$(PYTHON) solr/setup_schema.py

solr-load: solr-schema
	$(PYTHON) solr/load_documents.py "$(DATA)"

solr-queries: solr-up
	$(PYTHON) solr/run_queries.py "$(ROWS)"

solr-stop:
	$(COMPOSE) stop solr
