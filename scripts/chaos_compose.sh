#!/usr/bin/env bash
# D2 on Docker Compose: kill a share of the worker *fleet* mid-run, which
# is what the headline claim actually says ("kill 30% of workers mid-run
# and the invariant checker still reports zero violations").
#
#   scripts/chaos_compose.sh                      # kill 30% once
#   KILL_FRACTION=0.5 REPEAT=3 scripts/chaos_compose.sh
#
# This is different from `POST /chaos {"crash_probability": p}`, which
# makes every individual step have a p chance of hard-killing its worker.
# That one is a much harsher fault injector -- useful for proving
# idempotency, brutal for throughput. See the README's D2 notes.
set -euo pipefail

KILL_FRACTION="${KILL_FRACTION:-0.3}"
REPEAT="${REPEAT:-1}"
INTERVAL="${INTERVAL:-15}"
PROJECT="${PROJECT:-reflight}"

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }

for round in $(seq 1 "$REPEAT"); do
  mapfile -t workers < <(docker ps --filter "label=com.docker.compose.project=${PROJECT}" \
                                   --filter "label=com.docker.compose.service=worker" \
                                   --format '{{.Names}}' | shuf)

  total=${#workers[@]}
  if [ "$total" -eq 0 ]; then
    echo "no running worker containers in project '$PROJECT'" >&2
    echo "start some first:  docker compose up -d --scale worker=4 worker" >&2
    exit 1
  fi

  kill_count=$(awk -v t="$total" -v f="$KILL_FRACTION" 'BEGIN{ n=int(t*f+0.5); print (n<1?1:n) }')
  echo "round ${round}/${REPEAT}: SIGKILLing ${kill_count} of ${total} worker(s)"

  for name in "${workers[@]:0:$kill_count}"; do
    echo "  kill $name"
    docker kill --signal=KILL "$name" >/dev/null
  done

  if [ "$round" -lt "$REPEAT" ]; then sleep "$INTERVAL"; fi
done

cat <<'EOF'

Killed. Compose's `restart: unless-stopped` brings them back; any step
that was in flight was never acked, so RabbitMQ redelivers it and
`processed_messages` makes the replay a no-op.

Once every saga is terminal:
  curl -s -X POST http://localhost:8000/runs/<run-id>/invariants/check \
    -H "X-API-Key: dev-local-key-change-me"
EOF
