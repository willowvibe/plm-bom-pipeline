PYTHON ?= python3
DBT ?= dbt

DBT_DIR := dbt
RAW_DIR := $(CURDIR)/data/raw
DUCKDB_PATH := $(CURDIR)/data/plm.duckdb

.PHONY: data messy test dbt dbt-docs clean

data:
	$(PYTHON) -m generator --out data/raw

messy:
	$(PYTHON) -m generator --out data/raw-messy --defects all

test:
	$(PYTHON) -m pytest -q

# Build the staging and intermediate layers (and their tests, including the
# hand-checked BOM explosion unit test) into data/plm.duckdb.
dbt: data
	PLM_RAW_DIR=$(RAW_DIR) PLM_DUCKDB_PATH=$(DUCKDB_PATH) \
		$(DBT) build --select staging intermediate \
		--project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

dbt-docs: data
	PLM_RAW_DIR=$(RAW_DIR) PLM_DUCKDB_PATH=$(DUCKDB_PATH) \
		$(DBT) docs generate \
		--project-dir $(DBT_DIR) --profiles-dir $(DBT_DIR)

clean:
	rm -rf data/raw data/raw-messy data/plm.duckdb \
		dbt/target dbt/logs dbt/dbt_packages
