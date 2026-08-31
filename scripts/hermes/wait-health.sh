#!/usr/bin/env bash
set -Eeuo pipefail
bot=${1:?bot required}
scope=${2:?scope required}
seconds=${3:-180}
[[ $seconds =~ ^[0-9]+$ ]] || exit 64
deadline=$((SECONDS + seconds))
while (( SECONDS < deadline )); do
  /usr/local/libexec/hermes-fleet-health "$bot" "$scope" >/dev/null 2>&1 && exit 0
  sleep 2
done
/usr/local/libexec/hermes-fleet-health "$bot" "$scope"
