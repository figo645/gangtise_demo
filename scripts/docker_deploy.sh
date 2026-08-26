#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
IMAGE_NAME="${DOCKER_IMAGE_NAME:-gangtise-demo:latest}"
CONTAINER_NAME="${DOCKER_CONTAINER_NAME:-gangtise-demo-web}"
HOST_PORT="${HOST_PORT:-5001}"
CONTAINER_PORT="${CONTAINER_PORT:-5001}"
CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-${ROOT_DIR}/.gangtise_postgres_credentials}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found. Install Docker first." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not available. Start Docker Desktop or dockerd first." >&2
  exit 1
fi

if [ -f "$CREDENTIALS_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$CREDENTIALS_FILE"
  set +a
fi

RAW_APP_DB_HOST="${APP_DB_HOST:-${LOCAL_POSTGRES_HOST:-}}"
RAW_APP_DB_PORT="${APP_DB_PORT:-${LOCAL_POSTGRES_PORT:-5432}}"
RAW_APP_DB_NAME="${APP_DB_NAME:-${LOCAL_POSTGRES_DB:-sprint_dashboard}}"
RAW_APP_DB_USER="${APP_DB_USER:-${LOCAL_POSTGRES_USER:-postgres}}"
RAW_APP_DB_PASSWORD="${APP_DB_PASSWORD:-${LOCAL_POSTGRES_PASSWORD:-your_password}}"
RAW_VECTOR_DB_HOST="${VECTOR_DB_HOST:-${LOCAL_VECTOR_DB_HOST:-$RAW_APP_DB_HOST}}"
RAW_VECTOR_DB_PORT="${VECTOR_DB_PORT:-${LOCAL_VECTOR_DB_PORT:-$RAW_APP_DB_PORT}}"
RAW_POSTGRES_DB="${POSTGRES_DB:-$RAW_APP_DB_NAME}"
RAW_POSTGRES_USER="${POSTGRES_USER:-$RAW_APP_DB_USER}"
RAW_POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$RAW_APP_DB_PASSWORD}"
GANGTISE_RUNTIME_ENV="${GANGTISE_RUNTIME_ENV:-local}"

APP_DB_HOST="$RAW_APP_DB_HOST"
case "$APP_DB_HOST" in
  ""|127.0.0.1|localhost) APP_DB_HOST="host.docker.internal" ;;
esac
APP_DB_PORT="$RAW_APP_DB_PORT"
APP_DB_NAME="$RAW_APP_DB_NAME"
APP_DB_USER="$RAW_APP_DB_USER"
APP_DB_PASSWORD="$RAW_APP_DB_PASSWORD"
VECTOR_DB_HOST="$RAW_VECTOR_DB_HOST"
case "$VECTOR_DB_HOST" in
  ""|127.0.0.1|localhost) VECTOR_DB_HOST="$APP_DB_HOST" ;;
esac
VECTOR_DB_PORT="$RAW_VECTOR_DB_PORT"
POSTGRES_DB="$RAW_POSTGRES_DB"
POSTGRES_USER="$RAW_POSTGRES_USER"
POSTGRES_PASSWORD="$RAW_POSTGRES_PASSWORD"

other_container_on_port="$(docker ps --format '{{.Names}} {{.Ports}}' | awk -v port=":${HOST_PORT}->${CONTAINER_PORT}/tcp" '$0 ~ port {print $1}' | grep -vx "$CONTAINER_NAME" || true)"
if [ -n "$other_container_on_port" ]; then
  echo "Port ${HOST_PORT} is already published by another container: ${other_container_on_port}" >&2
  exit 1
fi

echo "Building image ${IMAGE_NAME}"
docker build -t "$IMAGE_NAME" "$ROOT_DIR"

existing_container_id="$(docker ps -a -q -f name="^/${CONTAINER_NAME}$" || true)"
if [ -n "$existing_container_id" ]; then
  existing_status="$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")"
  echo "Removing existing container ${CONTAINER_NAME} (${existing_status}) before redeploy."
  docker rm -f "$CONTAINER_NAME" >/dev/null
fi

RUN_ARGS=(
  -d
  --name "$CONTAINER_NAME"
  --restart unless-stopped
  -p "${HOST_PORT}:${CONTAINER_PORT}"
  --add-host=host.docker.internal:host-gateway
  -e "HOST=0.0.0.0"
  -e "PORT=${CONTAINER_PORT}"
  -e "APP_DB_HOST=${APP_DB_HOST}"
  -e "APP_DB_PORT=${APP_DB_PORT}"
  -e "APP_DB_NAME=${APP_DB_NAME}"
  -e "APP_DB_USER=${APP_DB_USER}"
  -e "APP_DB_PASSWORD=${APP_DB_PASSWORD}"
  -e "VECTOR_DB_HOST=${VECTOR_DB_HOST}"
  -e "VECTOR_DB_PORT=${VECTOR_DB_PORT}"
  -e "POSTGRES_DB=${POSTGRES_DB}"
  -e "POSTGRES_USER=${POSTGRES_USER}"
  -e "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}"
  -e "GANGTISE_RUNTIME_ENV=${GANGTISE_RUNTIME_ENV}"
)

# Keep host-owned authentication files out of the image while making the
# application-owned files available at the same project-root paths in /app.
for auth_file in .gangtise_session_secret .gangtise_openapi_credentials .gangtise_postgres_credentials; do
  if [ -f "$ROOT_DIR/$auth_file" ]; then
    RUN_ARGS+=( -v "$ROOT_DIR/$auth_file:/app/$auth_file:ro" )
  fi
done
RUN_ARGS+=( "$IMAGE_NAME" )

container_id="$(docker run "${RUN_ARGS[@]}")"

echo "Started container ${CONTAINER_NAME} (${container_id})."
docker ps --filter "name=^/${CONTAINER_NAME}$"
echo "URL: http://127.0.0.1:${HOST_PORT}"
