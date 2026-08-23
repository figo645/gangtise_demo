#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REQUIREMENTS_FILE="${ROOT_DIR}/requirements.txt"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
  echo "requirements.txt not found at ${REQUIREMENTS_FILE}" >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "${PYTHON_BIN} not found. Install Python 3 first." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -m venv --help >/dev/null 2>&1; then
  echo "Python venv module is not available. Install python3-venv first." >&2
  exit 1
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  echo "==> Creating virtual environment at ${VENV_DIR}"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "==> Upgrading pip"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip

echo "==> Installing Python dependencies from ${REQUIREMENTS_FILE}"
"${VENV_DIR}/bin/python" -m pip install -r "$REQUIREMENTS_FILE"

echo "==> Python environment ready."
echo "Activate with:"
echo "  source ${VENV_DIR}/bin/activate"
