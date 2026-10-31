#!/usr/bin/env bash
# Совместимая обёртка: реальная работа — в migrate_repo.sh
# (он вычищает личные фото из истории, а не только переносит ветку).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ $# -ge 1 ]; then
  DST_URL="$1" exec bash "$HERE/migrate_repo.sh" --dst "$1"
fi
exec bash "$HERE/migrate_repo.sh" "$@"
