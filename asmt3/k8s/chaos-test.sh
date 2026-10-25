#!/usr/bin/env bash
# Assignment 3 - Part D: how to repeat the three experiments on a REAL
# test cluster (kind / minikube). Synthetic environment only.
#
#   kind create cluster --name aitu-a3 --config k8s/kind-2nodes.yaml   (optional)
#   kubectl apply -f k8s/registration-service.yaml
#   ./k8s/chaos-test.sh e1|e2|e3
#
# In a second terminal keep load running and watch pods:
#   kubectl -n student-services get pods -w
#   kubectl -n student-services get endpointslices -l kubernetes.io/service-name=registration -w
set -euo pipefail
NS=student-services
ts() { date +%H:%M:%S.%3N; }

case "${1:-}" in
  e1)  # one replica: kill the process inside one pod (container restarts in place)
    POD=$(kubectl -n $NS get pods -l app=registration -o jsonpath='{.items[0].metadata.name}')
    echo "$(ts) inject: SIGKILL in $POD"
    kubectl -n $NS exec "$POD" -- kill -9 1 || true
    kubectl -n $NS wait --for=condition=Ready pod/"$POD" --timeout=120s
    echo "$(ts) recovered: $POD Ready again"
    ;;
  e2)  # all replicas at the same time
    echo "$(ts) inject: delete all registration pods"
    kubectl -n $NS delete pod -l app=registration --grace-period=0 --force --wait=false
    kubectl -n $NS rollout status deploy/registration --timeout=180s
    echo "$(ts) recovered: deployment available"
    ;;
  e3)  # database unavailable: scale the (synthetic) DB primary to 0
    echo "$(ts) inject: registration-db-primary scaled to 0"
    kubectl -n $NS scale statefulset/registration-db --replicas=0
    echo "observe: registration pods must stay Running (no liveness restarts)"
    kubectl -n $NS get pods -l app=registration
    ;;
  *) echo "usage: $0 e1|e2|e3"; exit 1;;
esac

# load generator suggestion (records status codes + latency per request):
#   kubectl -n $NS run load --rm -it --image=busybox -- sh -c \
#     'while true; do wget -q -O- -T 1 http://registration/health/ready >/dev/null \
#       && echo "$(date +%s) OK" || echo "$(date +%s) FAIL"; sleep 0.1; done'
