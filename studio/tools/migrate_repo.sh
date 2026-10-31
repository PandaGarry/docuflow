#!/usr/bin/env bash
# Переезд студии в целевой репозиторий: main = история БЕЗ личных фотографий.
#
# Зачем скрипт, а не «руками в терминале»: удалить файл коммитом недостаточно —
# он остаётся в истории и его видно любому, кто клонирует репозиторий. Здесь
# история переписывается (filter-branch), из неё вычищаются все личные снимки,
# и только после проверки «фото не осталось» делается push.
#
# Использование:
#   studio/engine/migrate_repo.sh                 # переехать (push --force в main)
#   studio/engine/migrate_repo.sh --dry-run       # только собрать и проверить
#   studio/engine/migrate_repo.sh --branch имя    # другую ветку источника
#   SRC=/path DST_URL=git@... studio/engine/migrate_repo.sh
#
# Требования: git, право записи в целевой репозиторий (Contents: read & write
# для приложения/токена, которым пушит git — одного «admin» у аккаунта мало).

set -euo pipefail

SRC="${SRC:-$(git rev-parse --show-toplevel)}"
DST_URL="${DST_URL:-https://github.com/PandaGarry/family_studio.git}"
DST_BRANCH="${DST_BRANCH:-main}"
BRANCH="${BRANCH:-$(git -C "$SRC" rev-parse --abbrev-ref HEAD)}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --branch) shift; BRANCH="$1" ;;
    --dst) shift; DST_URL="$1" ;;
    --dst-branch) shift; DST_BRANCH="$1" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "неизвестный аргумент: $1" >&2; exit 2 ;;
  esac
  shift
done

echo "источник : $SRC ($BRANCH)"
echo "цель     : $DST_URL → $DST_BRANCH"
echo "режим    : $([ "$DRY_RUN" = 1 ] && echo 'проверка без push' || echo 'push --force')"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "· клонирую зеркало…"
git clone --quiet --mirror --no-hardlinks "$SRC" "$TMP/studio.git"
cd "$TMP/studio.git"

echo "· вычищаю личные фото из истории…"
FILTER='git rm -r --cached --ignore-unmatch "studio/reference/*.webp" "studio/reference/*.jpeg" "studio/reference/*.jpg" "studio/reference/*.png"'
git filter-branch -f --index-filter "$FILTER" --prune-empty -- --all >/dev/null 2>&1 || {
  echo "✗ filter-branch не сработал" >&2; exit 1; }

# резервные refs/original держат старые (с фото) коммиты — их нельзя ни пушить,
# ни оставлять в клоне
for ref in $(git for-each-ref --format='%(refname)' 'refs/original'); do
  git update-ref -d "$ref"
done
git reflog expire --expire=now --all
git gc --prune=now --quiet

echo "· проверяю, что в истории не осталось снимков…"
LEFT="$(git log --all --name-only --pretty=format: | grep -E '^studio/reference/.*\.(webp|jpe?g|png)$' | sort -u || true)"
if [ -n "$LEFT" ]; then
  echo "✗ в истории всё ещё есть фото:" >&2
  echo "$LEFT" >&2
  exit 1
fi
echo "  ✓ чисто (остался только studio/reference/README.md)"

if ! git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
  echo "✗ в клоне нет ветки '$BRANCH'" >&2
  exit 1
fi

echo "  ветка $BRANCH = $(git rev-parse --short "$BRANCH") · коммитов: $(git rev-list --count "$BRANCH")"

if [ "$DRY_RUN" = 1 ]; then
  echo "✓ проверка пройдена, push не выполнялся"
  exit 0
fi

echo "· пушу…"
if ! git push --force "$DST_URL" "refs/heads/$BRANCH:refs/heads/$DST_BRANCH"; then
  cat >&2 <<'HINT'

✗ push отклонён. Почти всегда это права, а не код:
  1) Repo → Settings → GitHub Apps / Installations: у приложения должен быть
     доступ к целевому репозиторию с правом Contents: Read and write;
  2) если пушит токен — у него должен быть scope `repo` и доступ к организации;
  3) права аккаунта (admin/push в API) не заменяют права приложения.
Проверить, что именно доступно:  gh api repos/PandaGarry/family_studio --jq .permissions
HINT
  exit 1
fi

echo "✓ готово: $DST_URL ($DST_BRANCH)"
