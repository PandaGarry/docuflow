#!/usr/bin/env bash
# Партия 1 промо: все кадры собираются детерминированно из мастеров.
# Ни один герой здесь не генерируется — только вырезки из канона.
#
#   studio/promo/batch1.sh
#
# Результат: studio/promo/renders/*.png
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
SCENE="$PY studio/engine/promo_scene.py"
PROMO="$PY studio/engine/promo.py"
OUT=studio/promo/renders

mkdir -p "$OUT"

# P01 · постер «Мультсериал про свою семью» · 4:5
$SCENE scene --format post-4x5 --cast dad:hips,mom:stern,son:point \
    --bg studio/promo/plates/room-living-empty.png \
    --dad 0.50 --baseline 0.64 --out "$OUT/P01-art.png"
$PROMO compose "$OUT/P01-art.png" --format post-4x5 \
    --kicker "Сезон 1 · премьера 16 ноября" --title "Мультсериал про свою семью" \
    --sub "12 серий по 40 секунд" --out "$OUT/P01-post-4x5.png"

# P02/P03/P04 · карточки героев · 1:1 (студия, без фона-файла)
$SCENE cards
$PROMO compose "$OUT/P02-art.png" --format square --kicker "Папа" \
    --title "Всё под контролем" --out "$OUT/P02-square.png"
$PROMO compose "$OUT/P03-art.png" --format square --kicker "Мама" \
    --title "Ты серьёзно?" --out "$OUT/P03-square.png"
$PROMO compose "$OUT/P04-art.png" --format square --kicker "Сын" \
    --title "Понятно" --out "$OUT/P04-square.png"

# P05 · линейка семьи: фигуры на одной линии, подписи под ногами · 4:5
$SCENE lineup --format post-4x5 --cast dad:front,mom:front,son:front \
    --kicker "Линейка сезона" --dad 0.665 --baseline 0.775 --out "$OUT/P05-lineup.png"

# P08 · афиша даты · 4:5
$SCENE scene --format post-4x5 --cast dad:front,mom:front,son:front \
    --bg studio/promo/plates/room-living-empty.png \
    --dad 0.555 --baseline 0.665 --out "$OUT/P08-art.png"
$PROMO compose "$OUT/P08-art.png" --format post-4x5 \
    --kicker "Сезон 1" --title "16 ноября" --sub "12 серий по 40 секунд" \
    --out "$OUT/P08-post-4x5.png"

# P10 · открывашка Shorts · 9:16
$SCENE scene --format shorts-cover --cast dad:hips \
    --bg studio/promo/plates/room-living-vertical.png \
    --dad 0.52 --baseline 0.74 --out "$OUT/P10-art.png"
$PROMO compose "$OUT/P10-art.png" --format shorts-cover \
    --kicker "Серия 1" --title "Коробки" --sub "Премьера 16 ноября" --plate \
    --out "$OUT/P10-shorts-cover.png"

# доказательство: герой в кадре — пиксели мастера
$SCENE proof dad:front --scale 0.84
$SCENE proof mom:front --scale 0.84
$SCENE proof son:front --scale 0.84

# форматы, safe-зоны, вес
$PROMO verify "$OUT/P01-post-4x5.png" "$OUT/P02-square.png" "$OUT/P03-square.png" \
    "$OUT/P04-square.png" "$OUT/P05-lineup.png" "$OUT/P08-post-4x5.png" \
    "$OUT/P10-shorts-cover.png" | tail -2

# контакт-лист партии
$SCENE sheet
