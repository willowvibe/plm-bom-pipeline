PYTHON ?= python3

.PHONY: data messy test clean

data:
	$(PYTHON) -m generator --out data/raw

messy:
	$(PYTHON) -m generator --out data/raw-messy --defects all

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf data/raw data/raw-messy
