# 34 · Архитектура следующего движка студии

**Дата:** 2026-11-02 · **статус:** проектирование. Модули ниже не считаются
реализованными, если прямо не указано иное.

## 1. Что значит «более мощный движок»

Не ещё один большой скрипт с большим количеством синусов. Нужны:

1. один источник геометрии и идентичности персонажа;
2. редактируемые риги и актёрские кривые;
3. аудио с точной временной разметкой;
4. единый таймлайн тела, лица, камеры, контактов и звука;
5. независимый backend рендера, воспроизводимые сборки и проверяемый выпуск.

Blender отвечает за DCC/деформацию/свет/рендер, а наш Python-слой — за данные,
сборку, правила, контроль, версии и автоматизацию. Не заменять художественную
работу бесконечной генерацией самостоятельных рисунков.

## 2. Поток данных

```text
канон → approved model → body/face rig → versioned asset package
                                         ↓
сценарий → финальный дубль → phone alignment → speech curves
                                         ↓
сториборд → shot timeline → blocking → body / face / gaze / contacts
                                         ↓
                         binding → Blender scene → render frames/passes
                                         ↓
                         compositing → dialogue/music/foley → encode → QC
```

Ввод новой генерации изображения в середине готового шота запрещён без
проверки и новой версии ассета. Повторная запись реплики меняет hash аудио,
инвалидирует alignment/кривые/нужные кадры, а не просто подменяет звук в MP4.

## 3. Модули и ответственность

Пакет `studio/pipeline/` уже начат: contracts, timeline, Blender subprocess и
реальная диагностическая сцена — [технический MVP](38-BLENDER-MVP.md). Это
узкий smoke-срез, не реализация всех модулей таблицы. Внедрение остальных
частей — по задачам чек-листа; заглушки не считаются рабочими модулями.

Добавлен отдельный v2 preview path: внешний `.blend` package, semantic binding,
RSS/timeout guard и chunk checkpoints — [реализация 39](39-EXTERNAL-PACKAGES-AND-BOUNDED-WORKERS.md).
Это не закрывает generic production/approval workflow и character art gates.

| Модуль (проектируется) | Вход → выход | Граница ответственности / проверка |
|---|---|---|
| `project` | project config → resolved paths/settings | Версии, пути, профили выпуска; никакой анимации |
| `contracts` | JSON → validated objects | Типы, диапазоны, ссылки, миграции, half-open frame ranges |
| `assets` | asset ID/revision → package/manifest | Checksums, canonical ID, provenance, лицензии, approved revision |
| `speech` | WAV + transcript → phones/visemes/curves | Адаптер aligner, ручные исправления, коартикуляция; не TTS внутри рендера |
| `rig_binding` | semantic controls → actual rig bones/shapes | Проверка отсутствующих каналов, диапазонов, версий рига |
| `locomotion` | path + contact schedule → root/limb controls | IK, foot lock, heel/toe roll, start/stop; измеряемый slip |
| `acting` | beats + gesture clips → pose curves | Anticipation/hold/recovery, взгляд, реакция, корректирующие формы |
| `face` | emotion/gaze/blink/speech → bounded face controls | Владение каналами, конфликты, jaw/teeth/lip closure |
| `timeline` | shots + tracks → evaluated frame state | Точное время, смешивание слоёв, seed, события и приоритеты |
| `backends/blender` | evaluated state + asset package → scene/frame passes | Только DCC adapter; запуск отдельным процессом с timeout и exit code |
| `jobs` | shot ranges + manifest → resumable jobs | Cache, invalidation, retries, worker limits; не скрывает ошибки кадра |
| `composite` | linear passes + color config → display frames | Цвет, premult alpha, тени, DOF/blur; не «исправляет» лишние руки |
| `audio` | immutable stems → final mix | Диалог отдельно, ducking, loudness/true peak, отсутствие рассинхрона |
| `delivery` | frames + mix → MP4/SRT/poster/QC | Метаданные, полное декодирование, publish gate |
| `quality` | state/render/audio + thresholds → reports | Численные проверки плюс отдельная художественная приёмка |

**Реально добавленный служебный модуль этого этапа:**
`studio/tools/production_status.py` — валидация плана, генерация чек-листа,
снимок окружения. Это не реализация перечисленных анимационных модулей.

## 4. Общие контракты (PIPE-01, пока спецификация)

У каждого документа: `schema_version`, стабильный ID, `revision`, provenance.
Не отождествлять новую JSON-схему с уже существующей схемой `scene.py`.
Перенос идёт через явный adapter и тесты; старый renderer не читает новые поля
«по удаче».

### Project / время / координаты

- Master timebase — рациональная частота, первоначально `24/1` fps.
- Аудио — 48 000 Hz после подготовительного resample с сохранением исходника.
- Frame ranges — `[start_frame, end_frame)`, нумерация с нуля.
- Время кадра `f`: `f / fps`; audio sample index — округление рационального
  `f × sample_rate / fps`. При 24 fps это ровно 2000 сэмплов/кадр.
- Нельзя накапливать `t += 1/fps` и получать дрейф. Случайности задаются seed.
- Канонический мир: метры, правая система, Z вверх, +Y вперёд персонажа;
  `.L/.R` — анатомическая сторона, не сторона экрана.
- Старый `rig3d.py` использует другие осевые соглашения. Нужен документированный
  adapter преобразования базиса/масштаба с тестом, не копирование углов вслепую.
- Внутренние углы — радианы; пользовательские поля с градусами явно имеют
  суффикс `_deg`. Цвет для композитинга — linear; display transform фиксируется.

### Asset package

Пакет содержит ID персонажа, approved reference revision, меш, rig revision,
материалы/текстуры, scale/rest pose, bounding volumes, semantic bindings,
набор клипов и лицевых форм, контрольные рендеры, checksums и provenance.

Файлы `.blend` не монолит сезона: отдельные библиотеки персонажей и сцены,
ссылки/overrides, сборка шота из версий пакетов. Large binaries и модельные
веса — во внешнем хранилище с checksum и лицензией; LFS или storage выбирается
и проверяется до размещения. Не коммитить гигабайты в обычный Git. Личные
фотореференсы не пересылать внешнему сервису без согласования.

### Rig binding

Минимальные семантические контролы:

```text
body.root, body.cog, body.pelvis, body.spine, body.head
arm.L/R.ik_target, arm.L/R.pole, hand.L/R.grip
leg.L/R.ik_target, leg.L/R.pole, foot.L/R.heel, foot.L/R.toe
eye.L/R.look_target, lid.L/R.close, brow.L/R.raise
jaw.open, lip.close, lip.round, lip.wide, lip.lower_bite
```

Это контракт, не требование буквального имени кости Blender. Для пальцев,
корректив и асимметрии добавляются каналы. Binding проверяет существование,
тип, диапазон, rest value и сторону каждого канала. Отсутствующий обязательный
контрол — ошибка сборки, не silently ignored key.

### Speech package

- Исходник и нормализованный WAV, фактический transcript, speaker/take,
  sample count/rate и checksum.
- Phone spans: symbol, start/end sample, словарь/набор фонем, источник разметки,
  confidence если доступен, флаг ручной проверки. Confidence не выдумывается.
- Viseme mapping, паузы, closures и articulation curves со своей revision.
- Результат ASR со словами без phone spans не проходит как точный phoneme
  alignment. Заметки «примерно по тексту» должны оставаться preview-only.
- После stretch/resample/монтажа дубля alignment пересчитывается либо переносится
  документированным преобразованием времени и перепроверяется.

### Shot / evaluated state

Шот содержит целочисленные frame boundaries, версии персонажей, stage,
camera, audio refs, body/face/gaze/contact tracks, lighting/color revision,
seed и render profile. Evaluated state — численные значения на кадр, без
вызовов image generation/TTS в `frame()`.

Пример структуры (проектируемый контракт, **не готовая команда renderer**):

```json
{
  "schema_version": 1,
  "shot_id": "control-dad-01",
  "frame_range": [0, 192],
  "fps": {"num": 24, "den": 1},
  "actors": [{"id": "dad", "asset_revision": "approved-revision-required"}],
  "tracks": ["body", "speech", "gaze", "face", "contacts"],
  "render_profile": "review-1080p"
}
```

Значение `approved-revision-required` — явно пример, не существующая модель.
В production manifest нужны реальные revisions и hashes.

### Render / delivery manifest

Фиксируются scene/asset/audio/config hashes, renderer/plugins/build, color
config, frame range, seed, machine capabilities, times, peak memory,
фактически созданные кадры и checksum финала. Частично созданный шот не
называется законченным. Job ID зависит от содержимого, а не от mtime файлов.

## 5. Приоритеты слоёв и оценка движения

Порядок: root/path → locomotion → body acting → arm/hand contacts → gaze →
facial emotion → speech with closure constraints → correctives → secondary
motion → camera/render.

- Опорная стопа задаётся относительно поверхности в мире. Боб таза не может
  после IK унести её в сторону. Финальный contact solve проверяется повторно.
- Контакт кисти с кепкой/бородой имеет explicit target и weight; поверх него
  не накладывается произвольная дрожь головы.
- Коартикуляция не открывает губы в обязательном bilabial closure.
- У эмоции и речи не два независимых `mouth_open`; speech владеет артикуляцией,
  эмоция — совместимыми остаточными каналами. Конфликт фиксируется тестом.
- Веки не становятся полупрозрачными; моргание — деформация/поза века.
- Вторичная анимация ограничена и следует движению, не создаёт случайный шум.
- «На двойках» — выбор стилизации, не обязательный глобальный quantizer.
  Опоры, lipsync и быстрые жесты при необходимости оцениваются на единицах.
  Сравнить варианты в G6; не считать 60 fps автоматически более качественным.

## 6. Рендер, производительность и устойчивость

- Сначала короткая серия тестовых кадров: native 1080p, единый color transform,
  прозрачность/тени, качество денойзинга и отсутствие temporal flicker.
- Cache: assets → speech → evaluated state → scene → frame passes → comp → encode.
  Изменение субтитров не пересчитывает симуляцию походки.
- Кадры хранятся как последовательность; используем temp file + atomic rename.
  Проверяем размер/декодирование/checksum. Результат другого manifest не resume.
- Worker pool ограничен доступной RAM/VRAM. Число ядер не равно безопасному
  количеству Blender-процессов. Сначала измерение 1 worker, затем 2.
- Retry только для временных сбоев, с лимитом. Ошибочный rig binding не
  ретраится бесконечно и не заменяется предыдущим кадром.
- Измеряем median/P95 frame time, startup overhead, peak RSS/VRAM, render size,
  engine/device/samples. GPU-ускорение не заявляется до реального замера.

## 7. Повторное использование текущего кода

| Сейчас | Решение |
|---|---|
| `rig3d.py`, `animation.py` | Сохранить математические тесты и идеи IK/контактов; адаптировать оси и смысл root motion |
| `face.py` | Оставить API параметров/эмоций как референс; текстовый lip_sync только для preview |
| `facefx.py`, `limited.py`, `rig2d.py` | Поддерживать legacy 2,5D-превиз, не расширять имитацию скрытых поверхностей |
| `audio.py` | Переиспользовать синтез и FFmpeg-рецепты после проверки stem/sample/loudness contracts |
| `scene.py`, `render_pilot.py` | Рецепты/миграционный adapter, не делать из монолита второй production backend |
| `qa.py`, `selftest.py` | Сохранить существующие проверки; добавить реальные deformation/contact/audio-sync tests |
| PNG-лица и позы | Использовать как дизайн/pose library/reference, не как готовый трёхмерный риг |

Миграция постепенная: пока новый backend не проходит G6, legacy renderer не
удаляется. Новая папка с классами без проходящего реального шота не считается
новым движком.


### Технический body-срез r2 · 2026-11-03

[Документ 40](40-BODY-RIG-AND-CONTACT-PROBES.md) фиксирует отдельный r2
пакет: цельные indexed garments, 49 костей, leg IK, articulated fingers.
Optional v2 preview probes измеряют evaluated sole vertices в world space и
fingertips относительно posed hand bone; stance/finger gates не выводятся
из координат empty targets. Это узкий body fixture, не принятые ART/RIG/MOT
задачи и не production approval schema. Поддержка IK/FK switch, correctives,
face/phone pipeline и формальная приёмка остаются незавершёнными.
