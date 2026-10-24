#!/usr/bin/env bash
# Пересборка мультика «Уборка».
#
#   ./build.sh                      # вырезать персонажей + звук + видео + субтитры
#   ./build.sh --preview 2 8.5 24   # только статичные кадры (проверка вёрстки)
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

echo "▶ 1/4 вырезание персонажей по хромакею"
"$PY" scripts/cutout.py

echo "▶ 2/4 музыка, эффекты и микс с озвучкой"
"$PY" scripts/make_audio.py

echo "▶ 3/4 рендер видео"
"$PY" scripts/render.py

echo "▶ 4/4 субтитры"
"$PY" scripts/make_subs.py

echo "✓ готово: campaigns/toys/out/toys-cleanup.mp4 (+ .srt)"
