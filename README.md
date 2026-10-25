# family_studio — студия семейного мультсериала

> **Стиль выбран: B — стилизованный объём.** Правила — [`docs/13-STYLE-B.md`](docs/13-STYLE-B.md).
> Мастер-ассеты героев и процесс заготовок — [`docs/14-ASSET-PIPELINE.md`](docs/14-ASSET-PIPELINE.md).
> Переезд в репозиторий `family_studio` — [`docs/15-REPO-MIGRATION.md`](docs/15-REPO-MIGRATION.md).

Репозиторий-студия: здесь лежат **не просто видео**, а полный производственный
процесс — герои, стиль, движок анимации, сценарии серий, QA-чеклисты и
пошаговый план. Любая серия пересобирается из исходников одной командой.

## Что внутри

```
docs/                 документация студии (читать по порядку, 00 → 11)
studio/
  reference/          референсы реальной семьи (для дизайна героев)
  style-tests/        тесты стилей: A / B / C / D — выбрать один
  characters/         персонажи: character.json + мастера + производные ассеты
  library/            библиотеки-данные: позы, эмоции, гардероб, причёски, скелеты
  engine/             ядро: kit, puppet, face, rig, artgen, core_demo, selftest, QA
  out/                результаты: превизы, демо-ролики, отчёты
  episodes/           сценарии серий (shot list в JSON) + собранные mp4
  assets/             фоны, реквизит, звук
  fonts/              Montserrat + Nunito (латиница + кириллица, OFL)
  tools/prompts/      промпт-шаблоны генерации арта
```

## Быстрый старт

```bash
python3 -m venv .venv
.venv/bin/pip install pillow numpy imageio-ffmpeg fonttools brotli

# ядро: персонажи, позы, эмоции, одежда — всё в JSON (docs/16-CORE.md)
.venv/bin/python studio/engine/kit.py list chars
.venv/bin/python studio/engine/kit.py show dad
.venv/bin/python studio/engine/kit.py validate
.venv/bin/python studio/engine/kit.py prompt dad --pose wave --expr joy

# превиз без генерации: поза + эмоция + одежда за секунду
.venv/bin/python studio/engine/puppet.py preview --char dad --pose think --expr smirk
.venv/bin/python studio/engine/kit.py sheet dad     # 6 поз × 6 эмоций
.venv/bin/python studio/engine/kit.py faces dad     # крупные планы всех эмоций

# живая анимация: позы, эмоции, липсинк -> studio/out/core-demo.mp4
.venv/bin/python studio/engine/core_demo.py

# авторинг без кода: новая поза / эмоция
.venv/bin/python studio/engine/kit.py pose-save lean_wall --bones "spine:-6,head:-3" --label "У стены"
.venv/bin/python studio/engine/kit.py expr-save smug --face "lid=0.35,smile=0.35,mouth_skew=0.55"

# проверки ядра (36 штук, ~0.4 с) и бюджеты производительности
.venv/bin/python studio/engine/selftest.py
.venv/bin/python studio/engine/bench.py --assert

# заготовки ассетов: нарезка turnaround, вырезка, реестр, контакт-листы, проверка
.venv/bin/python studio/engine/artgen.py slice
.venv/bin/python studio/engine/artgen.py cut
.venv/bin/python studio/engine/artgen.py registry
.venv/bin/python studio/engine/artgen.py sheet
.venv/bin/python studio/engine/artgen.py verify

# демо старого рига и авто-QA
.venv/bin/python studio/engine/rig_demo.py          # -> studio/out/rig-demo.mp4
.venv/bin/python studio/engine/qa.py --assets studio/characters
```

## Герои: мастер-ассеты (стиль B)

| Герой | Turnaround (3 вида) | Портрет-идентичность | Виды | Позы |
|-------|--------------------|----------------------|------|------|
| Папа | ✅ | ✅ | 3/3 | point ✅ · wave/think/carry/surprise ⏳ |
| Мама | ✅ | ✅ | 3/3 | stern ✅ · wave/think/carry/surprise ⏳ |
| Сын | ✅ | ✅ | 3/3 | point ✅ · wave/think/carry/surprise ⏳ |

`⏳` — в `studio/characters/registry.json` уже лежат готовые промпты: каждая
новая поза генерируется **с мастерами в референсах**, поэтому лицо не «съезжает».

## Ядро: гибкость без перегенерации

Персонаж — это `character.json`, а не набор картинок. Из него выводится всё:
промпт для арта, скелет с нужными пропорциями, лицо, одежда.

- **27 поз** (`library/poses.json`, включая зеркальные через `mirror_of`),
  **28 эмоций** (`library/expressions.json`), **27 вещей** (`library/wardrobe.json`),
  **11 причёсок** — всё данные.
- **Лицо — 20 параметров**, а не картинка: эмоции смешиваются, липсинк идёт из
  текста, микромимика не даёт лицу «застыть».
- **Одежда меняется за секунду** — и в промпте (перегенерация), и в кукле
  (мгновенный превиз).
- **Ключи ассетов**: после правки одежды/причёски `kit.py stale` показывает, что
  именно устарело. Ничего не перегенерируется вслепую.
- **Кукла** (`puppet.py`) рисует кадр из JSON: 6×6 поз/эмоций на одном листе,
  хромакей-фон, любая смена одежды — без обращения к модели.
- **Авторинг без кода**: `kit.py pose-save` / `kit.py expr-save` добавляют новую
  позу или эмоцию прямо из терминала (с проверкой костей, параметров и диапазонов),
  зеркальная поза — одна строка `"mirror_of": "wave"`.
- **Зеркало и IK проверены числом, а не на глаз**: двойное зеркало возвращает
  позу с точностью `1e-16`, IK попадает в цель с промахом `0.0000 %` длины руки
  (`bench.py`), недостижимая цель даёт прямую руку строго по направлению.
- **Скорость**: кадр 540×960 в суперсэмплинге ×2 — 163 мс (было 332 мс),
  превиз 360×640 — 25 мс. Бюджеты зафиксированы в `bench.py --assert`, чтобы
  регресс по скорости ловился тестом, а не «стало как-то медленнее».

Полная карта ядра, API и рецепты («новая поза», «новый персонаж», «сменить
одежду») — [`docs/16-CORE.md`](docs/16-CORE.md).

Демо рига — техническая сцена на процедурном «болванчике» (не финальный арт).
Она показывает именно механику: IK-изгибы локтей, anticipation, прыжок со
сквош-стретчем, вторичная анимация головы, мигание. Герои сериала будут
собраны на этом же скелете из нарисованных слоёв.

## Статус проекта

| Этап | Что | Статус |
|------|-----|--------|
| 0 | Уборка репозитория, каркас студии | ✅ готово |
| 1 | Тесты стилей (4 варианта × 2 кадра) | ✅ готово, **ждём ваш выбор** (`docs/12`) |
| 2 | Арт-библия героев (turnaround, позы, мимика) | 🟡 мастера готовы, позы в работе |
| 3 | Движок рига: скелет, IK, вторичная анимация | ✅ работает, демо собрано |
| 4 | Липсинк и озвучка серии | ⏳ схема готова |
| 5 | Пилотная серия 1 | ⏳ сценарий в `docs/07` |
| 6 | Конвейер производства сезона | ⏳ план в `docs/08` |

## Документация

| Документ | О чём |
|----------|-------|
| [`docs/00-VISION.md`](docs/00-VISION.md) | Идея сериала, аудитория, тон, чем цепляет |
| [`docs/01-STACK.md`](docs/01-STACK.md) | Стек, почему именно он, альтернативы |
| [`docs/02-PIPELINE.md`](docs/02-PIPELINE.md) | Пайплайн производства: от идеи до mp4 |
| [`docs/03-CHARACTER-BIBLE.md`](docs/03-CHARACTER-BIBLE.md) | Герои: внешность, характер, реквизит |
| [`docs/04-STYLEGUIDE.md`](docs/04-STYLEGUIDE.md) | Стиль, палитра, линии, композиция, текст |
| [`docs/05-ANIMATION.md`](docs/05-ANIMATION.md) | Как делается «живая» анимация и почему |
| [`docs/06-QA-CHECKLIST.md`](docs/06-QA-CHECKLIST.md) | Брак, автоматические проверки, приёмка |
| [`docs/07-SERIES-PLAN.md`](docs/07-SERIES-PLAN.md) | Сезон 1: 12 серий и сквозной сюжет |
| [`docs/08-ROADMAP.md`](docs/08-ROADMAP.md) | Пошаговый план: что делаем и в каком порядке |
| [`docs/09-PROMPT-COOKBOOK.md`](docs/09-PROMPT-COOKBOOK.md) | Промпты, негативы, консистентность героев |
| [`docs/10-AUDIO.md`](docs/10-AUDIO.md) | Голоса, музыка, звук, громкость |
| [`docs/11-LICENSING.md`](docs/11-LICENSING.md) | Лицензии и права на образы семьи |
| [`docs/12-STYLE-TESTS.md`](docs/12-STYLE-TESTS.md) | Сравнение 4 стилей (история решения) |
| [`docs/13-STYLE-B.md`](docs/13-STYLE-B.md) | **Выбранный стиль B**: правила, риски, анимация |
| [`docs/16-CORE.md`](docs/16-CORE.md) | **Ядро**: персонажи, позы, эмоции, одежда, API, CLI |
| [`docs/14-ASSET-PIPELINE.md`](docs/14-ASSET-PIPELINE.md) | Заготовки: мастера, реестр, команды, добавление героя |
| [`docs/15-REPO-MIGRATION.md`](docs/15-REPO-MIGRATION.md) | Переезд в репозиторий `family_studio` |

## Приватность

Личные фотографии семьи **не хранятся в git** (ни в рабочей копии, ни в истории):
`studio/reference/` содержит только описание того, что нужно положить локально
(см. `studio/reference/README.md`), а сами файлы перечислены в `.gitignore`.
Из истории они вычищены `git filter-branch`, поэтому публичный репозиторий не
содержит личных снимков. Подробности — [`docs/11-LICENSING.md`](docs/11-LICENSING.md).

## Важно

Сериал — **вымышленная комедия по мотивам**, а не документальный портрет.
Образы героев созданы по мотивам референсных фото и участвуют с согласия семьи.
Шрифты — SIL OFL, музыка и звук синтезируются в репозитории.
