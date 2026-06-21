#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-}"
if [[ -z "$MODE" ]]; then
  echo "Usage: bash scripts/setup_controlled_exec_sandbox.sh {targetport|scale|assign}" >&2
  exit 2
fi

CTX="$(kubectl config current-context)"
if [[ "$CTX" != *kind* ]]; then
  echo "Refusing to set up sandbox outside a Kind-like context. current-context=$CTX" >&2
  exit 1
fi

kubectl create ns test-social-network --dry-run=client -o yaml | kubectl apply -f - >/dev/null

if [[ "$MODE" == "targetport" || "$MODE" == "scale" ]]; then
  cat <<'YAML' | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: user-service
  namespace: test-social-network
spec:
  selector:
    app: user-service
  ports:
    - name: http
      port: 9090
      targetPort: 9999
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service
  namespace: test-social-network
spec:
  replicas: 0
  selector:
    matchLabels:
      app: user-service
  template:
    metadata:
      labels:
        app: user-service
    spec:
      containers:
        - name: user-service
          image: nginx:1.25
          ports:
            - containerPort: 9090
YAML
  echo "Sandbox ready for $MODE: Service targetPort=9999, Deployment replicas=0"
elif [[ "$MODE" == "assign" ]]; then
  kubectl delete deployment user-service -n test-social-network --ignore-not-found=true >/dev/null
  cat <<'YAML' | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: user-service
  namespace: test-social-network
spec:
  selector:
    app: user-service
  ports:
    - name: http
      port: 9090
      targetPort: 9090
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service
  namespace: test-social-network
spec:
  replicas: 1
  selector:
    matchLabels:
      app: user-service
  template:
    metadata:
      labels:
        app: user-service
    spec:
      nodeSelector:
        kubernetes.io/hostname: extra-node
      containers:
        - name: user-service
          image: nginx:1.25
          ports:
            - containerPort: 9090
YAML
  echo "Sandbox ready for assign: Deployment nodeSelector kubernetes.io/hostname=extra-node"
else
  echo "Unknown mode: $MODE" >&2
  exit 2
fi

kubectl get deploy,svc -n test-social-network
