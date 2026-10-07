.PHONY: up down reset build logs ps migrate test test-integration lint fmt \
        demo-d1 demo-d2 demo-d3 demo-d6 demo-d7 finops invariants k3d-up k3d-down chaos

API ?= http://localhost:8000
KEY ?= dev-local-key-change-me

# ---- stack ----------------------------------------------------------------
up:
	docker compose up -d --build

down:
	docker compose down

reset:                      ## wipe volumes too (fresh Postgres/RabbitMQ/MinIO)
	docker compose down -v

build:
	docker compose build

logs:
	docker compose logs -f

ps:
	docker compose ps

migrate:
	docker compose run --rm migrate

# ---- quality --------------------------------------------------------------
lint:
	ruff check src tests scripts

fmt:
	ruff check --fix src tests scripts

test:
	PYTHONPATH=src pytest tests/unit -q

# Stops the consumers first: the integration tests share the live Postgres
# and RabbitMQ, and a running relay can pick up a test's transient outbox
# row before its cleanup deletes it.
test-integration:
	docker compose stop relay planner worker
	PYTHONPATH=src POSTGRES_HOST=localhost POSTGRES_PORT=$${POSTGRES_PORT:-5433} \
		REDIS_HOST=localhost REDIS_PORT=$${REDIS_PORT:-6379} \
		PARTNERS_HOST=localhost PARTNERS_PORT=8100 \
		pytest tests/integration -q; \
	status=$$?; docker compose up -d relay planner worker; exit $$status

# ---- demos (section 14) ---------------------------------------------------
demo-d1:                    ## greedy vs CP-SAT on the same scenario
	python scripts/measure_run.py --preset storm --seed 42 --strategy greedy --label "D1 greedy"
	python scripts/measure_run.py --preset storm --seed 42 --strategy cpsat  --label "D1 cpsat"
	@echo "Now open the dashboard's Compare page."

demo-d2:                    ## kill 30% of the worker fleet mid-run
	docker compose up -d --scale worker=4 worker
	python scripts/measure_run.py --preset storm --seed 42 --strategy greedy --label "D2" & \
	sleep 12; KILL_FRACTION=0.3 REPEAT=3 INTERVAL=12 bash scripts/chaos_compose.sh; wait

demo-d3:                    ## 50% ticketing failure -> compensation, no leaked holds
	python scripts/measure_run.py --preset small --seed 7 --strategy greedy \
		--partner-failure 0.5 --label "D3 partner outage"

demo-d6:                    ## one airline capped to 1 concurrent step
	curl -s -X POST $(API)/fairness -H "X-API-Key: $(KEY)" \
		-H "Content-Type: application/json" -d '{"default_cap":1}'
	python scripts/measure_run.py --preset storm --seed 42 --strategy greedy --label "D6 fairness"
	@echo "Parked steps land on saga.delay.2s -- check it in the RabbitMQ UI."
	curl -s -X POST $(API)/fairness -H "X-API-Key: $(KEY)" \
		-H "Content-Type: application/json" -d '{"default_cap":8}'

demo-d7:                    ## cascading delay down one tail number
	@docker compose exec -T postgres psql -U $${POSTGRES_USER:-reflight} -d $${POSTGRES_DB:-reflight} -c "\
	SELECT f.tail_number, count(*) AS legs, \
	       count(*) FILTER (WHERE d.type='CANCELLATION') AS cascade_cancelled, \
	       count(*) FILTER (WHERE d.type='DELAY') AS delayed \
	FROM disruption_events d JOIN flights f ON f.id = d.target_flight_id \
	WHERE d.cause = 'CASCADE' GROUP BY f.tail_number ORDER BY legs DESC LIMIT 5;"

chaos:                      ## kill a share of workers right now
	bash scripts/chaos_compose.sh

# ---- reports --------------------------------------------------------------
finops:                     ## make finops RUN=<run-id>
	@test -n "$(RUN)" || { echo "usage: make finops RUN=<run-id>"; exit 1; }
	@curl -s "$(API)/runs/$(RUN)/finops?format=markdown" -H "X-API-Key: $(KEY)"

invariants:                 ## make invariants RUN=<run-id>
	@test -n "$(RUN)" || { echo "usage: make invariants RUN=<run-id>"; exit 1; }
	@curl -s -X POST "$(API)/runs/$(RUN)/invariants/check" -H "X-API-Key: $(KEY)"

# ---- kubernetes (P1) ------------------------------------------------------
k3d-up:                     ## k3d cluster + KEDA + manifests
	bash scripts/k3d_up.sh

k3d-down:
	k3d cluster delete reflight
