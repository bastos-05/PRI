COMPOSE ?= docker compose
VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
DATA ?= data/final.jsonl
ROWS ?= 10
JUDGE_SCRIPT ?= avaliar_solr.py
QUERY ?= all
CONFIG ?= all
TOP ?= 20
STATE ?= .judgments/$(CONFIG)-$(QUERY).json

QUERIES_A ?= solr/eval/config/queries_a
QUERIES_B_INITIAL ?= solr/eval/config/queries_b_initial
QUERIES_B_FINAL ?= solr/eval/config/queries_b_final
QUERIES_B_AND ?= $(QUERIES_B_FINAL)/q05and.json

.PHONY: solr-judge

.DEFAULT_GOAL := help

.PHONY: help venv build up run start stop down ps logs solr solr-up solr-schema solr-load solr-queries solr-stop

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
	  'make solr-judge    Open relevance judging (QUERY=all CONFIG=all TOP=20)' \

venv:
	@test -x "$(VENV)/bin/python" || python3 -m venv "$(VENV)"
	@"$(PYTHON)" -c 'import requests' 2>/dev/null || "$(PYTHON)" -m pip install requests

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

solr-schema: solr-up venv
	$(PYTHON) solr/setup_schema.py

solr-load: solr-schema venv
	$(PYTHON) solr/load_documents.py "$(DATA)"

solr-queries: solr-up venv
	$(PYTHON) solr/run_queries.py "$(ROWS)"

solr-stop:
	$(COMPOSE) stop solr

solr-judge: venv
	@case "$(CONFIG)" in \
		all)       set -- --run "A=$(QUERIES_A)" --run "B_inicial=$(QUERIES_B_INITIAL)" --run "B_final=$(QUERIES_B_FINAL)" ;; \
		a)         set -- --run "A=$(QUERIES_A)" ;; \
		b-inicial) set -- --run "B_inicial=$(QUERIES_B_INITIAL)" ;; \
		b-final)   set -- --run "B_final=$(QUERIES_B_FINAL)" ;; \
		b-and)       set -- --run "B_AND=$(QUERIES_B_AND)" ;; \
		b-compare)   set -- --run "B_final=$(QUERIES_B_FINAL)/0005.json" --run "B_AND=$(QUERIES_B_AND)" ;; \
		*)         echo "CONFIG inválida. Usa all, a, b-inicial, b-and, b-compare
		 ou b-final." >&2; exit 2 ;; \
	esac; \
	if [ -f "$(STATE)" ]; then \
		"$(PYTHON)" "$(JUDGE_SCRIPT)" --state "$(STATE)"; \
	else \
		$(MAKE) solr-up || exit $$?; \
		if [ "$(QUERY)" != "all" ]; then set -- "$$@" --query "$(QUERY)"; fi; \
		"$(PYTHON)" "$(JUDGE_SCRIPT)" "$$@" --top "$(TOP)" --state "$(STATE)"; \
	fi