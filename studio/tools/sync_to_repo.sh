#!/usr/bin/env bash
# Перенос ветки студии из публичного репозитория в новый (например, приватный
# family_studio), к которому у агента нет доступа.
#
# Запуск (на вашей машине):
#   bash studio/tools/sync_to_repo.sh git@github.com:PandaGarry/family_studio.git
#
# Что делает:
#   1) клонирует публичный репозиторий с веткой студии;
#   2) добавляет ваш новый репозиторий как remote;
#   3) пушит ветку и main в новый репозиторий.
# Секретов и токенов в скрипте нет — только адреса.
set -euo pipefail

TARGET="${1:?укажите адрес нового репозитория, например git@github.com:user/family_studio.git}"
SOURCE="${SOURCE:-https://github.com/PandaGarry/docuflow.git}"
BRANCH="${BRANCH:-arena/303d70d8-docuflow}"
WORK="$(mktemp -d)"

echo "▶ клонирую $SOURCE"
git clone --quiet "$SOURCE" "$WORK/family_studio"
cd "$WORK/family_studio"
git checkout --quiet "$BRANCH"

echo "▶ добавляю новый remote: $TARGET"
git remote add target "$TARGET"

echo "▶ догружаю историю всех веток"
git fetch --quiet "$SOURCE" '+refs/heads/*:refs/remotes/source/*'

echo "▶ пушу ветку студии и main"
git push target "$BRANCH":"$BRANCH"
if git rev-parse --verify --quiet "source/main" >/dev/null; then
  git push target "source/main:main"
fi

echo "✓ готово. Дальше:"
echo "  • откройте PR из ветки $BRANCH в main нового репозитория"
echo "  • при желании удалите studio/reference (личные фото) из публичного"
echo "  • вернитесь с доступом к репозиторию, чтобы я продолжил работу напрямую"
rm -rf "$WORK"
