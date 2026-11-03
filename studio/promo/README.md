# studio/promo — промо-конвейер

Всё, что нужно, чтобы из мастеров героев получить готовый рекламный кадр:
референсы, промпт, бриф, типографику и проверку формата.

```
canon/identity.json   замок идентичности: пропорции, запреты, костюмы, стиль
canon/formats.json    форматы площадок: размеры, safe-зоны, «мёртвые» области, шрифты
canon/cutouts.json    кадры героев из мастеров — единственный источник героев в кадре
plates/               пустые фоны (генерируются без людей)
refs/                 сгенерировано: карточки героев, линейка семьи, лист идентичности
briefs/               сгенерировано: бриф на каждый пост (кадры из мастеров + команда сборки)
copies/               сгенерировано: подборки текстов по каналам
renders/              готовые креативы: <ID>-art.png (плата) и <ID>-<формат>.png (финал)
renders/rejected/     запись о забракованной первой партии (почему так нельзя)
```

## Быстрый старт

```bash
python3 -m venv .venv
.venv/bin/pip install pillow

# 1. референсы и замер пропорций по мастерам
.venv/bin/python studio/engine/promo.py refs

# 2. промпт для ПУСТОГО фона (герои не генерируются вообще)
.venv/bin/python studio/engine/promo.py prompt --format post-4x5 \
    --scene "living room with plain cardboard boxes, daylight from a window"

# 2б. плата: фон + герои из мастеров
.venv/bin/python studio/engine/promo_scene.py scene --format post-4x5 \
    --cast dad:hips,mom:stern,son:point \
    --bg <плата.png> \
    --dad 0.50 --baseline 0.64 --out studio/promo/renders/P01-art.png

# 2в. доказательство, что герой не перерисован
.venv/bin/python studio/engine/promo_scene.py proof dad:front

# 2г. линейка семьи: фигуры на одной линии, подписи под ногами
.venv/bin/python studio/engine/promo_scene.py lineup --format post-4x5 \
    --cast dad:front,mom:front,son:front --out studio/promo/renders/P05-lineup.png

# 3. брифы и тексты по всей кампании
.venv/bin/python studio/engine/promo.py briefs
.venv/bin/python studio/engine/promo.py copy --channel telegram

# 4. типографика поверх готового арта (текст НИКОГДА не просим у модели)
#    --plate — подложка под текст: нужна на пёстрых кадрах и на карточках героев
.venv/bin/python studio/engine/promo.py compose studio/promo/renders/P01-art.png \
    --format post-4x5 --kicker "СЕЗОН 1" --title "Папа всё продумал" \
    --sub "12 серий по 40 секунд" --plate --out studio/promo/renders/P01-post-4x5.png

# 5. проверка формата и безопасных зон
.venv/bin/python studio/engine/promo.py verify studio/promo/renders/P01-post-4x5.png

# 6. данные кампании и канона не разъехались?
.venv/bin/python studio/engine/promo.py check
.venv/bin/python studio/engine/promo.py plan
```

## Форматы

| Ключ | Размер | Где |
|------|--------|-----|
| `yt-thumb` | 1280×720 | превью YouTube |
| `shorts-cover` | 1080×1920 | шортс, сторис |
| `post-4x5` | 1080×1350 | лента Telegram / VK |
| `square` | 1080×1080 | карусель, кросспост |
| `vk-cover` | 1590×400 | обложка сообщества VK |
| `avatar` | 800×800 | аватар канала |

## Правила, которые зашиты в код

1. **Герой не генерируется.** В кадр идёт вырезка из мастера
   (`canon/cutouts.json`). Генерация — только для пустого фона и реквизита.
2. **Текст — только слоем.** В промпт фона уходит запрет на текст; кириллицу
   пишем сами.
3. **Порядок героев один:** папа, мама, сын (слева направо). Максимум трое.
4. **Масштаб по канону голов,** подошвы на общей линии, под ними тень.
5. **Заголовок проверяется по safe-зонам и `ui`-прямоугольникам** площадки.
6. **Кадр без PASS от `verify` и `proof` не публикуется.**

Подробно: [`docs/34-IDENTITY-LOCK.md`](../../docs/34-IDENTITY-LOCK.md),
[`docs/33-PROMO-ART.md`](../../docs/33-PROMO-ART.md),
[`docs/34-IDENTITY-LOCK.md`](../../docs/34-IDENTITY-LOCK.md),
[`docs/40-CHARACTERS.md`](../../docs/40-CHARACTERS.md),
[`docs/41-CHARACTERS-BIBLE.md`](../../docs/41-CHARACTERS-BIBLE.md).

## Плакаты прогрева

```bash
.venv/bin/python studio/engine/promo_poster.py all     # 9 плакатов
.venv/bin/python studio/engine/promo_poster.py sheet   # контакт-лист
.venv/bin/python studio/engine/promo_poster.py make quote --key mom:stern \
    --line1 "Ты" --line2 "серьёзно?" --who мама --out studio/promo/renders/x.png
```

Режимы: `announce`, `quote`, `silhouette`, `portrait`, `faces`, `meme`. Стратегия
и подводки — `docs/40-CHARACTERS.md`.

