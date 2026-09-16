#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR/scripts/runtime_process_lib.sh"

stop_all_runtime_processes "$SCRIPT_DIR"
echo "Stopped all Gangtise runtime processes for $SCRIPT_DIR."
