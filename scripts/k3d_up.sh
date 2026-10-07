#!/usr/bin/env bash
# Stands up the k3d cluster for the KEDA autoscaling demo (D5, section 10).
#
# Needs: docker, k3d, kubectl, helm. Everything else (images, manifests,
# credentials) comes from this repo and .env.
set -euo pipefail

CLUSTER="${CLUSTER:-reflight}"
API_NODEPORT="${API_NODEPORT:-30080}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for tool in k3d kubectl helm docker; do
  command -v "$tool" >/dev/null || { echo "missing required tool: $tool" >&2; exit 1; }
done

[ -f "$ROOT/.env" ] || { echo "no .env -- copy .env.example first" >&2; exit 1; }
# shellcheck disable=SC1091
set -a; source "$ROOT/.env"; set +a

echo "==> creating k3d cluster '$CLUSTER'"
if ! k3d cluster list "$CLUSTER" >/dev/null 2>&1; then
  k3d cluster create "$CLUSTER" \
    --agents 1 \
    --port "${API_NODEPORT}:30080@loadbalancer" \
    --wait
fi

echo "==> building and importing reflight:dev"
docker build -t reflight:dev "$ROOT"
k3d image import reflight:dev -c "$CLUSTER"

echo "==> generating secrets.env from .env"
cat > "$ROOT/k8s/base/secrets.env" <<EOF
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}
RABBITMQ_DEFAULT_USER=${RABBITMQ_DEFAULT_USER}
RABBITMQ_DEFAULT_PASS=${RABBITMQ_DEFAULT_PASS}
MINIO_ROOT_USER=${MINIO_ROOT_USER}
MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}
MINIO_BUCKET=${MINIO_BUCKET}
API_STATIC_KEY=${API_STATIC_KEY}
EOF

echo "==> installing KEDA"
helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install keda kedacore/keda --namespace keda --create-namespace --wait

echo "==> applying manifests"
kubectl apply -k "$ROOT/k8s/base"
kubectl -n reflight rollout status deploy/postgres --timeout=180s
kubectl -n reflight rollout status deploy/rabbitmq --timeout=240s
kubectl -n reflight rollout status deploy/api --timeout=180s

echo "==> wiring KEDA's RabbitMQ trigger to the real credentials"
kubectl -n reflight create secret generic keda-rabbitmq \
  --from-literal=host="amqp://${RABBITMQ_DEFAULT_USER}:${RABBITMQ_DEFAULT_PASS}@rabbitmq.reflight.svc.cluster.local:5672/" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -k "$ROOT/k8s/keda"

cat <<EOF

Cluster is up.

  kubectl -n reflight get pods -w          # watch replicas climb and fall
  kubectl -n reflight port-forward svc/api 8000:8000

Then drive a mega run against http://localhost:8000 and watch
'kubectl -n reflight get hpa,scaledobject' while the queue drains.
EOF
