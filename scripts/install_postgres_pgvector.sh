#!/usr/bin/env bash

set -euo pipefail

# Ubuntu/Debian installer for the application's local PostgreSQL and pgvector.
PG_MAJOR="${PG_MAJOR:-16}"
PGVECTOR_VERSION="${PGVECTOR_VERSION:-0.8.5}"
DB_NAME="${APP_DB_NAME:-sprint_dashboard}"
DB_USER="${APP_DB_USER:-gangtise_app}"
CREDENTIALS_FILE="${POSTGRES_CREDENTIALS_FILE:-/root/gangtise_postgres_credentials}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root: sudo $0" >&2
  exit 1
fi

if [ ! -f /etc/os-release ]; then
  echo "This installer supports Ubuntu and Debian only." >&2
  exit 1
fi

# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) echo "Unsupported OS: ${ID:-unknown}" >&2; exit 1 ;;
esac

if ! command -v apt-get >/dev/null 2>&1; then
  echo "apt-get is required." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
echo "==> Installing PostgreSQL ${PG_MAJOR} build dependencies"
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg build-essential git lsb-release \
  software-properties-common

install -d -m 0755 /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | gpg --dearmor --yes -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg
CODENAME="${VERSION_CODENAME:-$(lsb_release -cs)}"
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg] http://apt.postgresql.org/pub/repos/apt ${CODENAME}-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list

apt-get update
apt-get install -y \
  "postgresql-${PG_MAJOR}" \
  "postgresql-client-${PG_MAJOR}" \
  "postgresql-server-dev-${PG_MAJOR}"

PG_CONFIG="$(command -v pg_config || true)"
if [ -z "$PG_CONFIG" ]; then
  PG_CONFIG="/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config"
fi
if [ ! -x "$PG_CONFIG" ]; then
  echo "pg_config not found for PostgreSQL ${PG_MAJOR}." >&2
  exit 1
fi

echo "==> Installing pgvector ${PGVECTOR_VERSION} for PostgreSQL $($PG_CONFIG --version)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
git clone --depth 1 --branch "v${PGVECTOR_VERSION}" \
  https://github.com/pgvector/pgvector.git "$BUILD_DIR/pgvector"
make -C "$BUILD_DIR/pgvector" PG_CONFIG="$PG_CONFIG" OPTFLAGS=""
make -C "$BUILD_DIR/pgvector" PG_CONFIG="$PG_CONFIG" install

if [ -z "${APP_DB_PASSWORD:-}" ]; then
  if command -v openssl >/dev/null 2>&1; then
    APP_DB_PASSWORD="$(openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 32)"
  else
    APP_DB_PASSWORD="$(date +%s)-$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')"
  fi
fi

echo "==> Enabling and starting PostgreSQL ${PG_MAJOR}"
systemctl enable postgresql
systemctl start postgresql

echo "==> Creating application role and database"
if ! runuser -u postgres -- psql -Atqc "SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'" | grep -q '^1$'; then
  runuser -u postgres -- psql --set ON_ERROR_STOP=1 \
    -v db_user="$DB_USER" -v db_password="$APP_DB_PASSWORD" \
    -c 'CREATE ROLE :"db_user" LOGIN PASSWORD :'"'"'db_password'"'"';'
else
  runuser -u postgres -- psql --set ON_ERROR_STOP=1 \
    -v db_user="$DB_USER" -v db_password="$APP_DB_PASSWORD" \
    -c 'ALTER ROLE :"db_user" WITH LOGIN PASSWORD :'"'"'db_password'"'"';'
fi

if ! runuser -u postgres -- psql -Atqc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q '^1$'; then
  runuser -u postgres -- createdb -O "$DB_USER" "$DB_NAME"
fi

runuser -u postgres -- psql --set ON_ERROR_STOP=1 -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"
VECTOR_VERSION="$(runuser -u postgres -- psql -Atqc "SELECT extversion FROM pg_extension WHERE extname = 'vector'" -d "$DB_NAME" | tr -d '[:space:]')"

cat > "$CREDENTIALS_FILE" <<EOF
APP_DB_HOST=127.0.0.1
APP_DB_PORT=5432
APP_DB_NAME=$DB_NAME
APP_DB_USER=$DB_USER
APP_DB_PASSWORD=$APP_DB_PASSWORD
LOCAL_POSTGRES_HOST=127.0.0.1
LOCAL_POSTGRES_PORT=5432
LOCAL_POSTGRES_DB=$DB_NAME
LOCAL_POSTGRES_USER=$DB_USER
LOCAL_POSTGRES_PASSWORD=$APP_DB_PASSWORD
EOF
chmod 600 "$CREDENTIALS_FILE"

echo "==> PostgreSQL: $($PG_CONFIG --version)"
echo "==> pgvector: ${VECTOR_VERSION:-not detected}"
echo "==> Database: ${DB_NAME}"
echo "==> Role: ${DB_USER}"
echo "==> Credentials written to: ${CREDENTIALS_FILE}"
echo "Installation completed successfully."
