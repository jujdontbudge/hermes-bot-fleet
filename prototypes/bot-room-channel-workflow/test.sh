#!/bin/sh
# One-command headless acceptance runner for this throwaway prototype.
set -eu
cd "$(dirname "$0")"
node test.js
