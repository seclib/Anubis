#!/usr/bin/env sh
set -eu

IMAGE="${ANUBIS_DISTRIBUTED_IMAGE:-anubis/distributed:latest}"

if command -v kustomize >/dev/null 2>&1; then
  kustomize build infra/k8s/base | sed "s#anubis/distributed:latest#$IMAGE#g" | kubectl apply -f -
else
  kubectl kustomize infra/k8s/base | sed "s#anubis/distributed:latest#$IMAGE#g" | kubectl apply -f -
fi
