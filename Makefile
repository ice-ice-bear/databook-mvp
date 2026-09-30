DEMO = docker compose -f compose.yaml -f compose.demo.yaml
DATE ?= 2026-09-27

.PHONY: demo test report regenerate stop schedule api-demo api-report sync web
demo:
	$(DEMO) up -d --wait db
	$(DEMO) build worker example-api
	$(DEMO) run --rm worker init-db
	$(DEMO) run --rm worker run --date $(DATE) --csv data/adobe_mock_daily.csv
	uv run --locked sync_onedrive.py --date $(DATE)

test:
	uv run --locked test_adobe.py
	uv run --locked test_web.py
	uv run --locked test_schedule.py
	uv run --locked test_sync_onedrive.py
	$(DEMO) up -d --wait db
	$(DEMO) build worker example-api
	$(DEMO) run --rm -e LLM_PROVIDER=none -e DATA_PROVIDER=mock --entrypoint python worker test_pipeline.py
	$(DEMO) run --rm -e LLM_PROVIDER=none --entrypoint python worker test_query_workspace.py

report:
	$(DEMO) run --rm worker run --date $(DATE) --csv data/adobe_mock_daily.csv
	uv run --locked sync_onedrive.py --date $(DATE)

regenerate:
	$(DEMO) run --rm worker run --date $(DATE) --csv data/adobe_mock_daily.csv --regenerate
	uv run --locked sync_onedrive.py --date $(DATE)

stop:
	$(DEMO) stop db example-api

schedule:
	uv run --locked schedule.py --serve

api-demo:
	$(DEMO) build worker example-api
	$(DEMO) up -d --wait db example-api
	$(DEMO) run --rm worker init-db
	$(DEMO) run --rm -e DATA_PROVIDER=example_api worker run --date $(DATE) --regenerate
	uv run --locked sync_onedrive.py --date $(DATE)

api-report:
	$(DEMO) run --rm -e DATA_PROVIDER=example_api worker run --date $(DATE) --regenerate
	uv run --locked sync_onedrive.py --date $(DATE)

sync:
	uv run --locked sync_onedrive.py --date $(DATE)

web:
	$(DEMO) build worker example-api
	$(DEMO) up -d --wait db example-api
	$(DEMO) run --rm worker init-db
	uv run --locked web.py
