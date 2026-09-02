#!/usr/bin/env bash
set -euo pipefail

# Apply approved incremental packages in order. The single-package runner keeps
# checksums and skips packages already recorded for the target environment.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="${ROOT_DIR}/scripts/apply_database_release_package.sh"
BACKUP_SCRIPT="${ROOT_DIR}/scripts/create_database_release_backup.sh"

[[ "$#" -gt 0 ]] || { echo "Usage: $0 package_dir [package_dir ...]" >&2; exit 2; }

total="$#"
index=0
if [[ "${DATABASE_RELEASE_TARGET:-staging}" == "production" ]]; then
  "$BACKUP_SCRIPT"
  export DATABASE_RELEASE_PRODUCTION_BACKUP_READY=1
fi
for package_dir in "$@"; do
  index=$((index + 1))
  echo "==> [${index}/${total}] 开始增量包：${package_dir#${ROOT_DIR}/}"
  "${RUNNER}" "${package_dir}"
  echo "==> [${index}/${total}] 增量包完成"
done

echo "==> 所有增量包执行完成：${total} 个"
