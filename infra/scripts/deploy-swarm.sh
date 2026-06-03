#!/usr/bin/env sh
set -eu

STACK="${ANUBIS_SWARM_STACK:-anubis}"

docker stack deploy \
  -c infra/swarm/anubis-stack.yml \
  "$STACK"
