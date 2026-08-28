#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -m unittest discover -s tests/acceptance -p 'test_production_catalog.py' -v
