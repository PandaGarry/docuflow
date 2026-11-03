# family_studio — студия семейного мультсериала

> **Стиль выбран: B — стилизованный объём.** Правила — [`docs/13-STYLE-B.md`](docs/13-STYLE-B.md).
> Мастер-ассеты героев и процесс заготовок — [`docs/14-ASSET-PIPELINE.md`](docs/14-ASSET-PIPELINE.md).
> Переезд в репозиторий `family_studio` — [`docs/15-REPO-MIGRATION.md`](docs/15-REPO-MIGRATION.md).

Репозиторий-студия: герои, стиль, несколько поколений экспериментального
движка, рецепты роликов и документация. Production-переход к полноценным
ригам, походке и артикуляции ещё предстоит; готовность подтверждается
контрольными сценами, а не наличием кода или плана.

## Текущая работа · Rain → мама: реальная переработка головы R2, WIP

**[Эталон / отклонённый A7 / новая геометрия R2](studio/reviews/mom-head-form-r2/comparison-identity.png)** ·
[Три одинаковых clay ракурса A7/R2](studio/reviews/mom-head-form-r2/comparison-clay.png) ·
[Visual review / blockers](studio/reviews/mom-head-form-r2/visual-review.json) ·
[Процесс, реальные кадры и editable .blend](docs/48-MOM-PRIMARY-HEAD.md).

В отличие от предыдущего audit, **новая геометрия создана**. Голова перестроена
из официальной Rain, без накопления A1–A7 face fields: cheek/jaw/chin, объёмы
носа/губ, lid aperture и brow design. R1 просмотрен и не принят: жёсткие брови,
угловатый низ лица и ошибочная привязка lip controls к inner mouth surface.
R2 исправляет binding, смягчает brow/jaw, меняет lip/tip volumes. Оба прохода
имеют actual Blender frames, source recipes и native packed artifact.

**Это ещё не эталонная мама и не готовый риг.** Primary forms/характер требуют
доводки; blink/lash и symmetric-smile diagnostics визуально не прошли. Исходный
риг сохранён, но facial rest/attachment/corrective migration не завершён.
Hair/body/skin lookdev/wardrobe здесь не переделывались: это neutral head study.
Проверка повторного открытия реального R2 `.blend` запущена отдельно, не подменяется
PNG из процесса сборки. Art/user/production approval=false.

[Почему A7 отклонён, исправление метода](docs/47-MOM-FORM-RESET.md) ·
[Источник Rain и A1/A2](docs/44-RAIN-MOM-STUDY.md) ·
[A3–A5 и failures](docs/45-RAIN-FACE-A3.md) · [История A6/A7](docs/46-RAIN-PHOTO-GUIDED-A6.md).
Личные фото остаются ignored/local, не читаются CI/не публикуются; masters сохранены.
302 tests/native success не являются киноуровнем или художественной приёмкой.
Credit: Rain Rig (CC) Blender Foundation | studio.blender.org, modified CC BY4.0.

## Актуальный план развития движка · 2026-11-03

- **[План реализации и порядок этапов](docs/33-PRODUCTION-PLAN.md)** — аудит,
  зависимости, контрольные сцены 8/12 секунд, затем 40-секундная серия.
- **[Архитектура и модули](docs/34-ENGINE-ARCHITECTURE.md)** — Blender как
  кандидат DCC/backend, Python orchestration, контракты ригов, речи и сборки.
- **[Шлюзы качества](docs/35-QUALITY-GATES.md)** — опоры, артикуляция по записи,
  деформации, художественная приёмка и выпуск.
- **[Живой чек-лист](docs/36-PRODUCTION-TRACKER.md)** — генерируется из
  `studio/production/plan.json`, с зависимостями, blocker и evidence.
- **[Решения и журнал итераций](docs/37-DECISION-LOG.md)** ·
  [Навигация по документации](docs/README.md).
- **[Первый исполнимый Blender-срез](docs/38-BLENDER-MVP.md)** — контракты,
  subprocess, настоящий Cycles CPU, измерения и явные ограничения MVP.
- **[Внешний 3D-пакет и bounded workers](docs/39-EXTERNAL-PACKAGES-AND-BOUNDED-WORKERS.md)** —
  импорт `.blend`, ограничение памяти, проверяемое продолжение по батчам и
  неутверждённый объёмный блокинг папы.
- **[Body-прототип r2 и контактные измерения](docs/40-BODY-RIG-AND-CONTACT-PROBES.md)** —
  49 костей, IK ног, сгибаемые пальцы, цельная одежда и 3-секундный technical fixture.
- **[Проверка деформаций r3 и visual review](docs/41-DEFORMATION-REVIEW-R3.md)** —
  связные кисти, 51 кость с elbow helpers, 17 поз и 72 кадра проверки.
  Технический pass не означает красивую/принятую внешность.

Планирование и учёт работают без сторонних Python-пакетов:

```bash
python3 studio/tools/production_status.py validate
python3 studio/tools/production_status.py checklist --check
python3 -m unittest discover -s studio/tests -p test_production_status.py -v
```

Первоначальный снимок среды: `studio/production/environment.json` (до установки
runtime). Реальный Blender/FFmpeg smoke пройден: **24 кадра 1080p**,
IK/skinning/shape key, MP4 и полное декодирование; **98 unit tests** (70 MVP +
28 tracker) в первом этапе, затем **149 unit/process tests** с новым внешним
пакетом. Отдельный r2 body-срез добавляет ещё **35 tests**: вместе с
tracker — **184 unit/process tests**; r3 refinement добавляет 19, итог — **203**. R1 preview — 48 кадров 960×540; r2 —
72 кадра 640×360, проверка подошв и пальцев, не финальная модель или походка.
R3 — отдельный 3 s reach/curl/recovery, а не приёмка походки.
Команды, измерения и ограничения — в документах 38–41. Это не готовый production-движок и не артикуляция
по фактической записи. Старые сроки,
счётчики и планы ниже — история предыдущих этапов, не актуальный roadmap.

## Пробная серия для просмотра

**«Куда пропала буква P?» · версия 2** — [MP4, 40 секунд, 1080p](studio/out/pilot-letter-p.mp4).
Русский рассказчик, музыка, звуковые акценты и субтитры. Пять новых актёрских
поз, жест подсказки, касание кепки, реакция смеха и моргание.
Это **ограниченная 2,5D-анимация**, не полноценный 3D-мультфильм и не
заявление о достижении уровня большой телевизионной студии.
[Описание, ограничения и пересборка](docs/31-PILOT-LETTER-P.md) ·
[Ревизия ветки: убраны 37 производных файлов](docs/32-CLEANUP-AND-ACTING.md).

```bash
python3 -m venv .venv
.venv/bin/pip install -r studio/requirements.txt
.venv/bin/python -m unittest discover -s studio/tests -p test_pilot.py -v
.venv/bin/python studio/tools/render_pilot.py
```

В `studio/out/` отслеживаются только актуальные ролик, постер и README;
остальные результаты старых примеров ниже пересобираются, а не хранятся в Git.

## Пробная серия для просмотра

**«Куда пропала буква P?» · версия 2** — [MP4, 40 секунд, 1080p](studio/out/pilot-letter-p.mp4).
Русский рассказчик, музыка, звуковые акценты и субтитры. Пять новых актёрских
поз, жест подсказки, касание кепки, реакция смеха и моргание.
Это **ограниченная 2,5D-анимация**, не полноценный 3D-мультфильм и не
заявление о достижении уровня большой телевизионной студии.
[Описание, ограничения и пересборка](docs/31-PILOT-LETTER-P.md) ·
[Ревизия ветки: убраны 37 производных файлов](docs/32-CLEANUP-AND-ACTING.md).

```bash
python3 -m venv .venv
.venv/bin/pip install -r studio/requirements.txt
.venv/bin/python -m unittest discover -s studio/tests -v
.venv/bin/python studio/tools/render_pilot.py
```

В `studio/out/` отслеживаются только актуальные ролик, постер и README;
остальные результаты старых примеров ниже пересобираются, а не хранятся в Git.

## Что внутри

```
docs/                 документация студии (читать по порядку, 00 → 11)
studio/
  reference/          референсы реальной семьи (для дизайна героев)
  style-tests/        тесты стилей: A / B / C / D — выбрать один
  characters/         персонажи: character.json + мастера + производные ассеты
  library/            библиотеки-данные: позы, эмоции, гардероб, причёски, скелеты
  engine/             прежние kit, puppet, face, rig, artgen, core_demo, selftest, QA
  pipeline/           новый Blender MVP: contracts, timeline, subprocess, smoke QC
  schemas/            JSON Schema contracts (технический профиль v1)
  production/         план, version pins и компактные фактические отчёты
  out/                результаты: превизы, демо-ролики, отчёты
  scenes/             сцены-данные: актёры, позы/эмоции по времени, реплики, камера
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

# сцена из нескольких персонажей: камера, реплики, субтитры -> mp4
.venv/bin/python studio/engine/scene.py validate
.venv/bin/python studio/engine/scene.py render s01e01-shot01

# промо-шортс (титры, музыка, 18 с) -> studio/out/promo-s01.mp4
.venv/bin/python studio/engine/scene.py render promo-s01 --quality high
.venv/bin/python studio/engine/audio.py bed --seconds 18.6 --out studio/out/promo-bed.wav
.venv/bin/python studio/engine/audio.py mux --video studio/out/promo-s01-silent.mp4 \
    --audio studio/out/promo-bed.wav --out studio/out/promo-s01.mp4

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

## Статус проекта — исторический срез

Таблица ниже сохранена как история раннего этапа. Текущее состояние задач —
[живой чек-лист](docs/36-PRODUCTION-TRACKER.md); стиль B уже выбран.

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
| [`docs/10-AUDIO.md`](docs/10-AUDIO.md) | Голоса, музыка (синтез в репозитории), громкость |
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
