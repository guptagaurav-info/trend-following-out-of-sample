PY ?= python
export PYTHONPATH := src

.PHONY: all ingest run test clean
all: ingest run
ingest:
	$(PY) -m trendoos.ingest
run:
	$(PY) -m trendoos.pipeline
test:
	$(PY) -m pytest -q tests
clean:
	rm -rf reports/figures/*.png reports/metrics.json
