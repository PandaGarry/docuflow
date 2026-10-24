#!/usr/bin/env bash
# Полная пересборка концепт-ролика iPad Air.
#
#   ./build.sh                      # звук + видео
#   ./build.sh --preview 9 18.5 36  # только статичные кадры (проверка вёрстки)
#
# Требования: python3 (venv), пакеты pillow numpy imageio-ffmpeg fonttools brotli.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for candidate in "../../.venv/bin/python" "../.venv/bin/python" ".venv/bin/python" "python3"; do
  if [ -x "$candidate" ] || command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
[ -n "$PY" ] || { echo "python не найден"; exit 1; }

if [ "${1:-}" = "--preview" ]; then
  shift
  echo "▶ превью кадров"
  "$PY" scripts/render.py --preview "$@"
  exit 0
fi

echo "▶ 1/2 музыка, саунд-дизайн, микс с озвучкой"
"$PY" scripts/make_music.py

echo "▶ 2/2 рендер видео"
"$PY" scripts/render.py

echo "✓ готово: campaigns/ipad-air/out/ipad-air-promo.mp4"
