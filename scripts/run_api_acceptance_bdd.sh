#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${REAL_BDD_BASE_URL:-http://127.0.0.1:5001}"
TENANT="${REAL_BDD_TENANT:-laowang}"

case "${BASE_URL}" in
  *47.105.48.193*|*production*)
    if [[ "${REAL_BDD_ALLOW_WRITE_TARGET:-0}" != "1" ]]; then
      echo "Refusing API BDD against a production target because the suite creates temporary business records." >&2
      echo "Use staging/local, or explicitly set REAL_BDD_ALLOW_WRITE_TARGET=1 after review." >&2
      exit 2
    fi
    ;;
esac

if [[ -z "${REAL_BDD_USERNAME:-}" || -z "${REAL_BDD_PASSWORD:-}" ]]; then
  cat >&2 <<'EOF'
REAL_BDD_USERNAME and REAL_BDD_PASSWORD are required.
Use one command-line scope, or export them first:

  REAL_BDD_USERNAME='财经老王' REAL_BDD_PASSWORD='demo123' ./scripts/run_api_acceptance_bdd.sh

or:

  export REAL_BDD_USERNAME='财经老王'
  export REAL_BDD_PASSWORD='demo123'
  ./scripts/run_api_acceptance_bdd.sh
EOF
  exit 2
fi

echo "[api-bdd] target=${BASE_URL} tenant=${TENANT}"
echo "[api-bdd] preflight: HTTP API reachability"
curl --fail --silent --show-error --max-time "${REAL_BDD_PREFLIGHT_TIMEOUT_SECONDS:-10}" \
  -H 'Accept: text/html' "${BASE_URL%/}/login" >/dev/null

exec python3 "${ROOT_DIR}/tests/run_api_acceptance_bdd.py" \
  --base-url "${BASE_URL}" \
  --tenant "${TENANT}" \
  --username "${REAL_BDD_USERNAME}" \
  --password "${REAL_BDD_PASSWORD}"
