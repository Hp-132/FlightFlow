#!/usr/bin/env bash
# D2 on Kubernetes: kill a share of the worker pods mid-run and let the
# invariant checker prove nothing was lost.
#
#   scripts/chaos.sh            # kill 30% of worker pods, once
#   KILL_FRACTION=0.5 scripts/chaos.sh
#   REPEAT=5 INTERVAL=10 scripts/chaos.sh
#
# The Compose equivalent is `POST /chaos {"crash_probability": 0.3}`,
# which makes the workers hard-exit from the inside instead.
set -euo pipefail

NAMESPACE="${NAMESPACE:-reflight}"
KILL_FRACTION="${KILL_FRACTION:-0.3}"
REPEAT="${REPEAT:-1}"
INTERVAL="${INTERVAL:-10}"

command -v kubectl >/dev/null || { echo "kubectl not found" >&2; exit 1; }

for round in $(seq 1 "$REPEAT"); do
  mapfile -t pods < <(kubectl -n "$NAMESPACE" get pods -l app=worker \
    -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | shuf)

  total=${#pods[@]}
  if [ "$total" -eq 0 ]; then
    echo "no worker pods in namespace $NAMESPACE" >&2
    exit 1
  fi

  kill_count=$(awk -v t="$total" -v f="$KILL_FRACTION" 'BEGIN{ n=int(t*f); print (n<1?1:n) }')
  echo "round $round/$REPEAT: killing $kill_count of $total worker pod(s)"

  for pod in "${pods[@]:0:$kill_count}"; do
    kubectl -n "$NAMESPACE" delete pod "$pod" --grace-period=0 --force --wait=false
  done

  [ "$round" -lt "$REPEAT" ] && sleep "$INTERVAL"
done

echo
echo "Workers will be rescheduled automatically. Once every saga is terminal:"
echo "  curl -s -X POST \$API/runs/<run-id>/invariants/check -H \"X-API-Key: \$API_KEY\""
