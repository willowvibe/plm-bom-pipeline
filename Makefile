PYTHON ?= python3
DBT ?= dbt

DBT_DIR := dbt
RAW_DIR := $(CURDIR)/data/raw
DUCKDB_PATH := $(CURDIR)/data/plm.duckdb

.PHONY: data messy test dbt dbt-docs verify-defects clean

data:
	$(PYTHON) -m generator --out data/raw

messy:
	$(PYTHON) -m generator --out data/raw-messy --defects all

test:
	$(PYTHON) -m pytest -q

# Build every layer (staging, intermediate, marts) and all tests, including
# the seven defect tests and the hand-checked BOM explosion unit test, into
# data/plm.duckdb.
dbt: data
	PLM_RAW_DIR=$(RAW_DIR) PLM_DUCKDB_PATH=$(DUCKDB_PATH) \
		$(DBT) build \
		--project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

# Prove defect attribution: clean data has zero failures, each single seeded
# defect fails exactly its own test, and all seven together fail exactly seven
# tests. A second build with those seven tests excluded proves all 188 built-in
# model, generic, unit and mart nodes still pass. Uses $(DBT), so
# `make verify-defects DBT=/path/to/dbt` works.
verify-defects:
	$(PYTHON) scripts/verify_defects.py --dbt $(DBT)

dbt-docs: data
	PLM_RAW_DIR=$(RAW_DIR) PLM_DUCKDB_PATH=$(DUCKDB_PATH) \
		$(DBT) docs generate \
		--project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

clean:
	rm -rf data/raw data/raw-messy data/plm.duckdb \
		dbt/target dbt/logs dbt/dbt_packages
