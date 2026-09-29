DEMO = docker compose -f compose.yaml -f compose.demo.yaml
DATE ?= 2026-09-27

.PHONY: demo test report regenerate stop schedule
demo:
	$(DEMO) up -d --wait db
	$(DEMO) build worker
	$(DEMO) run --rm worker init-db
	$(DEMO) run --rm worker run --date $(DATE) --csv data/adobe_mock_daily.csv

test:
	$(DEMO) up -d --wait db
	$(DEMO) build worker
	$(DEMO) run --rm --entrypoint python worker test_pipeline.py

report:
	$(DEMO) run --rm worker run --date $(DATE) --csv data/adobe_mock_daily.csv

regenerate:
	$(DEMO) run --rm worker run --date $(DATE) --csv data/adobe_mock_daily.csv --regenerate

stop:
	$(DEMO) stop db

schedule:
	python3 schedule.py
