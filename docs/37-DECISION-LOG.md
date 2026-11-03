# 37 · Журнал решений и отчёты итераций

Этот журнал дополняет исторический `26-LOG.md`. Записи append-only: принятое
ранее решение не стирается, новое решение указывает, что именно изменилось.
Актуальные статусы задач находятся в `studio/production/plan.json`.

## ADR-001 · DCC вместо нового физического движка

**Дата:** 2026-11-02 · **статус:** выбран путь для проверки; backend ещё не принят.

**Контекст:** нужны свободные повороты, скрытые поверхности, руки, походка и
лицевая артикуляция. PNG-библиотека и локальные деформации не дают этого
надёжно. В репозитории уже есть несколько поколений экспериментальных ригов.

**Решение:** проверяем Blender как основной DCC/renderer, наш код — production
orchestration. Не переписываем полноценный DCC/рендерер с нуля. Начинаем с
headless Cycles CPU, затем измеряем доступные ускорители/превиз.

**Альтернативы:** дальнейший единый PNG-риг ограничивает движение; чистая
видеогенерация не гарантирует идентичность и редактируемость; собственный
SDF-рендерер не решает художественный моделинг и лицевой риг.

**Условие пересмотра:** ENV-02/G1 не проходит. Фиксируем log и причину,
согласуем другую среду/worker. Не объявляем историческую неудачу Blender
доказательством невозможности всех новых вариантов.

## ADR-002 · Качественный ассет — самостоятельный этап

**Статус:** правило текущего плана.

Генерация изображений используется для концепта, уточнения одежды/мимики и
проверки канона. Она не объявляется автоматическим решением топологии, весов
и shape keys. Не нужен новый рисунок лица на каждый кадр речи. Меш, риг и
коррективы версионируются, проходят G2–G4, требуют художественной приёмки.

## ADR-003 · Сначала фактическая запись, потом lipsync

**Статус:** правило текущего плана; aligner ещё не выбран окончательно.

Речь привязана к immutable audio take. Для русского проверяем совместимость
aligner/словаря/acoustic model и права на веса; MFA — кандидат, не установленный
модуль. ASR word timestamps и амплитудный рот не считаются phone alignment.
Ручная фонемная разметка допустима как прозрачный MVP. Текстовый lip_sync из
старого движка остаётся только preview.

## ADR-004 · Вертикальный срез до масштабирования

**Статус:** правило текущего плана.

Сначала соло-сцена 8 секунд, затем 12 секунд с реакцией второго героя. Полный
сезон, массовая генерация и порт всех персонажей не начинаются до G6/G7.
Задача с файлами и зелёными unit tests не считается художественно принятой.

## ADR-005 · Состояния и доказательства вместо оптимистичных чекбоксов

**Статус:** введено в плановый пакет.

Источник задач — `studio/production/plan.json`; `36-PRODUCTION-TRACKER.md`
генерируется инструментом. `done` требует закрытых зависимостей и evidence.
Для задач с визуальной приёмкой дополнительно нужен approval record конкретной
версии; агент не приписывает пользователю одобрение. CI/валидатор проверяют
структуру и наличие записи, но не способны доказать подлинность художественного
решения человека — это отдельный процесс.

Все не реализованные анимационные модули остаются planned. Не создаём десятки
пустых классов и не называем это мощным движком.

## ADR-006 · Воспроизводимость и доступ к ресурсам

**Статус:** правило текущего плана.

Версии фиксируются после runtime-пробы, не по слову «самый современный».
Лицензии, hashes и происхождение сторонних моделей проверяются до подключения.
Крупные бинарники не идут в обычный Git. Облачные расходы, публикация личных
фото и внешние сервисы не включаются без согласования. Интернет-доступ и
поддержка GPU проверяются фактически; доступность Python-пакета не означает
доступность его модельных весов.

## Итерация 2026-11-02 · План следующего production-этапа

**Запрос:** профессиональный план более мощного движка, походки, жестов,
мимики и полноценной артикуляции; подробная документация и чек-лист.

**Изменено:**

- Проведена ревизия существующих модулей и исторических планов.
- Подготовлены план 33, архитектура 34, QA-шлюзы 35, tracker 36 и этот журнал.
- Старые основные планы помечены как исторические, ссылки выведены в README.
- Добавлены машиночитаемые задачи, валидатор, генератор чек-листа, doctor и
  отдельные тесты служебного инструмента.

**Доказательства проверки:** `studio/production/verification.json` и
`studio/production/environment.json`. Здесь нет нового видеорендера или
нового готового 3D-ролика. Старые 65 engine checks и 9 pilot tests в этом
плановом этапе не объявляются повторно пройденными: их runtime-зависимости
проверяются doctor отдельно.

**Ограничения:** Blender не обнаружен при начальном осмотре; runtime/headless
smoke test ещё не выполнен. Художественные модели семьи и phone alignment
по фактической записи ещё не приняты. Доступность готового исторического MP4
не подменяет проверку воспроизводимости в текущей рабочей копии.

**Фактические проверки планового пакета:** 28/28 новых stdlib-тестов пройдены;
JSON-план из 28 задач валиден, Markdown-чек-лист совпадает с источником,
локальные ссылки активных документов проверены, compileall и
`git diff --check` завершились с кодом 0. Workflow GitHub Actions добавлен,
но его удалённый запуск не проверялся. Контрольные анимационные сцены не
рендерились в этой итерации.

**Дальше:** ENV-02, параллельно PIPE-01 и подготовка канона ART-01; не запуск
массовой генерации и не обещание уровня телевизионной студии.

## Шаблон следующей записи

```text
Дата / задача / revision:
Ожидалось:
Фактически изменено:
Команда проверки и exit code:
Артефакт и checksum/путь:
Результат: pass / fail / needs-review:
Замечания пользователя / approval record:
Известные ограничения:
Зависимые задачи / инвалидированные результаты:
Следующий шаг / blocker:
```

## ADR-007 · Технический MVP не закрывает production-контракты

**Дата:** 2026-11-02 · **статус:** реализован узкий вертикальный срез.

Введены семь JSON Schema v1, validator, семантический timeline, binding и
настоящий Blender subprocess. Но asset/project/shot v1 намеренно ограничены
synthetic probe. Внешний character package пока не загружается. Поэтому
PIPE-01 остаётся in_progress, а общий PIPE-02 не закрывается одним тестовым
роботом. Их acceptance уточнён в сторону внешнего model/rig package, а не
ослаблен ради зелёного статуса. Нет миграции Y-up → Z-up: несовместимые оси
явно отклоняются. Никакая техническая геометрия не выдаётся за семью.

## ADR-008 · Изолированный native fallback не является production-базой

**Дата:** 2026-11-02 · **статус:** разрешён только как sandbox-эксперимент.

Официальный bpy wheel не импортировался: семь отсутствующих системных
sonames. Для проверки CPU backend использованы девять настоящих библиотек
из pinned commit публичного distro mirror eXtern-OS (с GLX/GLdispatch).
Проверены Git blob SHA-1, размер и SHA-256, сохранены packaged copyright
notices. Никаких графических ABI-stubs, патча Blender или отката к PNG wobble.

Это не официальная подпись Debian/Ubuntu, не проверка уязвимостей старого
архива и не подтверждение актуальности Blender patch version. Поэтому
fallback требует явного opt-in, не попадает в Git бинарниками, не включается
по умолчанию. Добавлена ENV-04: поддерживаемая production OS/base image,
официальные native packages, integrity/security/licensing review и чистый
повторный smoke. До этого весь G1 не объявляется закрытым. Подробности и
команды — `38-BLENDER-MVP.md`.

## Итерация 2026-11-02 · Первая реализация и настоящий Blender smoke

**Запрос:** «приступай» — перейти от плана к реализации. Выполнен первый
технический срез, а не семейная серия.

**Фактически изменено:** seven local schemas v1, contracts/timebase,
semantic linear tracks и проверяемый binding, отдельный bpy worker,
IK-skinned диагностический mesh и jaw shape key, lighting/AgX,
playable `.blend`, PNG → H.264/AAC → полное video/audio decode,
quality report и artifact manifest. Библиотеки и Python environment изолированы
в игнорируемом cache; дублирующее первичное окружение и отменённые frame
пробы убраны. Семейные мастера и прежние исходники не удалены.

**Фактические проверки:**

- 70/70 новых MVP unit tests, 28/28 tracker tests, 98 всего.
- ENV-02: 24 PNG 1920×1080, 24 fps, 1 s; 14/14 smoke checks pass.
- Blender 4.5.0 build `8cb6b388974a`, Cycles CPU, 4 samples + denoise, AgX;
  FFmpeg 7.0.2-static, H.264 yuv420p + AAC 48 kHz mono. Worker, encode и оба
  decode — exit 0. MP4 — 179 499 bytes.
- Wall time 875.2084 s; peak renderer RSS 2 724 827 136 bytes (~2.54 GiB).
  Реальный affinity — 2 CPU, запрошено 8 threads: это не восемь ядер и не
  доказанная оптимизация. GPU не тестировался.
- IK residual max 1.78814e-7 m, bone length relative error max 3.14774e-7;
  вычисленная mesh vertex сдвинулась на 0.66538 m, jaw mesh — на 0.19 m.
- Реально проверены failure без native libs (exit 1, 0 PNG, no success
  manifest), hash-verified cache hit без нового worker и отказ на испорченной
  копии `.blend` с сохранённым размером. Исходный cache не испорчен.
- Экспортированный `.blend` открыт заново: кадры 0/12/23 воспроизводят
  keyed target/shape key без Python timeline application.
- `pip check`, compileall, plan validation, generated tracker и diff checks
  выполнены локально; итоговые команды/hashes — `verification.json`.
  Удалённый GitHub Actions не запускался; старые pilot/engine suites не
  выдаются за повторно пройденные.

**Evidence:** `studio/production/blender-smoke-report.json`,
`blender-negative-probes.json`, `blender-scene-reload.json`,
`blender-hardware-inventory.json`, `blender-runtime-attempts.json`,
`blender-requirements.lock`; описание — `38-BLENDER-MVP.md`.
Первый плановый отчёт сохранён как
`studio/production/planning-verification-2026-11-02.json`;
`verification.json` теперь содержит итог текущей реализации.

**Ограничения:** mirror native fallback не одобрен для production; version
pins не являются wheel-hash/security lock. Наблюдался рост RSS, причина
пока не профилирована. Нет доказательства стабильности 192/960 кадров,
memory-bounded batching/restart, production asset import, полноценного
лица, ходьбы или артикуляции по аудио. Технический робот не является новой
версией папы/сына; художественного approval нет. На основе этой пробы
нельзя обещать быстрый рендер семейной серии.

**Статусы:** ENV-02 done только как фактический smoke; PIPE-01 in_progress,
общий PIPE-02 planned (его smoke-срез работает, внешний package ещё нет).
Добавлена ENV-04 для поддерживаемой среды, integrity/security/licensing
review и stability/resource-budget проверки. 29 задач: 6 done, 1 in_progress,
22 planned. Полный G1 не закрыт.

**Дальше:** общий model/rig package contract и настоящий importer, bounded
worker/memory guard и воспроизводимая production-среда; канон ART-01.
Затем deformation-ready папа, body/face rig и 8-секундный контрольный шот.

## ADR-009 · Внешний пакет и ограниченное время жизни renderer

**Дата:** 2026-11-03 · **статус:** реализован preview-срез PIPE-04.

Рост RSS предыдущей CPU-пробы не объявляется устранённым native leak.
Вместо неограниченного цикла введены новый процесс на маленький chunk,
CPU affinity cap, sampled group RSS/timeout watchdog и завершение process
group на отказе. Это не hard cgroup и не защита от любого OOM.

Модель отдельно авторится в `.blend`; renderer импортирует объявленную
collection из проверенного snapshot, не создаёт папу/робота как fallback.
Версия 2 — явный `rig_preview`, а не скрытая миграция v1. Права/доверие и
художественное approval не следуют из SHA. Блокинг имеет `art_status=unreviewed`.
Generic production pipeline/approval contracts и ART/RIG задачи не закрыты.

## Итерация 2026-11-03 · Внешний блокинг папы и bounded preview

**Изменено:** packages/resources/render_package/package_worker, четыре v2
схемы, отдельная авторская recipe папы, checkpoint/attempt directories,
job lock, hash-verified resume, full MP4 decode. Дописаны 51 unit/process
тест и workflow без установки Blender. Подробная запись — документ 39.

**Фактически:** 48 кадров 960×540, 24 fps, 2 s, silent H.264 MP4,
105 358 bytes. 12 разных worker PID по 4 кадра; 1 chunk reused после
намеренной паузы (exit 75), 11 новых; первый checkpoint не изменился.
Peak renderer/group RSS 833 417 216 bytes (~795 MiB), budget 1536 MiB,
2 фактических threads. Сумма worker wall time 443.5461 s; wall time
продолжения 408.3461 s не включает первый батч до паузы.

**Проверки:** отсутствующие collection/control → реальные bpy jobs exit 1,
0 PNG, no complete chunk/manifest; низкий RSS budget реально остановил
Blender. Экспортированный `.blend` проигрывает ключи на семи проверенных
кадрах без нашего apply, max numeric error 1.43052e-7. Полное decode — 48
кадров с корректными PTS/timebase/dimensions. Все 149 тестов (51+70+28)
локально пройдены; remote Actions не запускался.

После полного прогона исправлен manifest edge case пустых diagnostic logs.
Текущим кодом выполнен отдельный 4-frame/2-worker live regression с pause,
resume и hashed zero-byte artifact; full cache hit и реальный отказ на
испорченном PNG также проверены. Байты regression PNG восстановлены,
основной 48-frame cache не менялся. Новому коду не приписывается повторный
48-frame render: producer hashes и обе интеграционные записи сохранены.

**Evidence:** `dad-preview-report.json`, `dad-package-integration.json`,
`package-empty-log-regression.json`, `package-short-regression-report.json`,
`dad-preview/package-r1.json`, новый `verification.json` в `studio/production/`.
Предыдущий итог 98 тестов архивирован как
`blender-mvp-verification-2026-11-02.json`; цифры не смешиваются с legacy suites.

**Статусы:** PIPE-04 done только как данный внешний bounded preview.
30 задач: 7 done, 1 in_progress (PIPE-01), 22 planned. Общий PIPE-02,
ENV-04, QA/ART/RIG и все контрольные 8/12/40 s сцены не приняты.

**Ограничения и дальше:** прототип папы — грубые объёмные заготовки,
не production topology/likeness. Нет ходьбы, пальцевого рига, полноценной
мимики или lipsync. Следом — общие production/approval contracts,
likeness/topology папы и body/face rig; поддерживаемая официальная среда
и длинный stress test остаются отдельными задачами. Новый preview нельзя
напрямую сравнивать по скорости/памяти с прошлым 1080p smoke.


## ADR-010 · Contact/finger gates берут evaluated geometry

**Дата:** 2026-11-03 · **статус:** реализован узкий RIG-00 прототип.

IK endpoint сам по себе не подтверждает контакт обуви с полом. Реальная
проба с неприкреплёнными к root skinned meshes проходила IK residual,
но давала 134.6 mm sole drift / 40 mm hover. Исправлены object parents.
Сохраняем четыре evaluated sole vertices в world space и tip-ring centers
в posed-hand-local space. Это ловит скольжение/поворот и не приписывает
root/wrist motion пальцевому ригу. Static-finger native negative действительно
отклоняется, несмотря на остальное движение. Это contact fixture, не физика
баланса/CoM и не автоматический art judge.

## Итерация 2026-11-03 · Body-прототип r2 и первый переступ

**Изменено:** отдельная r2 recipe, pure indexed loft module, цельные свитер/
брюки, 49-костный скелет с leg IK и тремя суставами каждого пальца. Рецепт r1
и канонические картинки сохранены. Optional v2 probes/dependency provenance,
измерения при рендере, stance/finger/bone failure gates, 35 новых pure tests.
Подробности и команды — документ 40.

**Фактически:** 72 кадра 640×360/24 fps/3 s silent MP4 (91 486 bytes),
18 разных bounded workers по 4 кадра, pause 75 → resume 0, 1 reused + 17 new.
Peak worker/group RSS 657 858 560 bytes (~627.4 MiB), 2 threads, 6 samples.
405.1877 s суммарного worker wall, 384.1924 s продолжения без первого chunk.
Full decode: 72 кадра/PTS/dimensions OK; completed-cache hash verification OK.

**Измерения:** sole drift 0.00433 mm, ground/penetration error 0.02997 mm,
IK residual 0.04498 mm, relative bone length error 3.502e-5. Все 72 rendered
measurements равны отдельной direct IR probe и native replay без apply.
Пять правых пальцев дают hand-local tip span 106.47–138.31 mm; реальная
заморозка finger tracks даёт <0.001 mm и ожидаемый fail (exit 1).

**Проверки/статусы:** реальный 4-frame negative render с поднятой стопой,
ошибочно объявленной stance, дал exit 1 без completed manifest. Все 184 unit/process tests (70+51+35+28) локально
пройдены; remote Actions не запускался. 31 задача: 8 done, 1 in_progress
(PIPE-01), 22 planned. Новый RIG-00 done — только данный технический срез;
ART-02, RIG-01, MOT-01, полный G3 и сцены 8/12/40 s не закрыты. Evidence —
`studio/production/dad-rig-*.json`; полный render manifest сохранён вне cache.
149-test receipt архивирован отдельно, historical robot 98-test receipt
также сохранён. `verification.json` обновлён после итоговых проверок.

**Ограничения/дальше:** грубые likeness/плечи/волосы/сгибы; кисть — шесть
пересекающихся closed surfaces, не финальная seamless hand topology.
Нет IK/FK switch, foot roll, correctives/extreme-pose suite, collision/CoM
simulation, живой мимики или lipsync. После technical spike нужны канон и
художественная переработка головы/плеч/кистей, extreme-pose fixtures, затем
face/phone pipeline. Generic contracts и официальная среда остаются открыты.


## ADR-011 · Extreme stills недостаточно; numeric pass не beauty approval

**Дата:** 2026-11-03 · **статус:** реализован r3 deformation experiment.

Сохраняем r1/r2 recipes и отдельный provenance r3. Кисть — связная all-quad
surface после authoring subdivision; runtime probes не теряют vertex IDs.
Симметрично калибруем rest elbow planes, плавно строим sleeve centerline,
добавляем две elbow helpers. 17 static poses не заменяют проверку всех
промежуточных кадров: такая проверка действительно нашла схлопывание,
пропущенное still-suite. Лимиты не ослаблены; исправлены геометрия, веса,
распределение локтевого изгиба и траектория wrist target.

Отдельно делаем native close-ups и like-for-like render comparison.
Agent visual review остаётся `approved=false`: ладонь плоская, wrist/cuff,
голова/волосы, мимика и актёрская пластика не доведены. Современный backend
и зелёные метрики не являются художественной приёмкой или likeness approval.

## Итерация 2026-11-03 · Проверка и переработка деформаций r3

**Результат:** 51 bone, связная closed all-quad кисть вместо 6 shells,
rest elbow errors уменьшены с 57.54/185.43 mm до ~0.0003 mm. Hermite sleeves,
armpit clearance, chest/clavicle blending и elbow deformation helpers.
17 static poses и все 72 кадра native QA проходят неизменённые heuristic
limits. Animated minimum area ratio 0.19442, maximum edge ratio 2.05797.
Это не collision/cloth simulation или полный production extreme-pose suite.

**Видео:** настоящий 72-frame/640×360/24 fps/3 s silent H.264, 57 997 bytes,
18 fresh bounded workers, peak RSS 666 009 600 bytes. Полный decode/PTS/
dimensions и completed-cache resume проверены. Direct IR, native replay
без apply и render-worker measurements совпали. Frozen-finger native negative
правильно дал exit 1 при сохранении motion руки/запястья.

**Visual review:** отрендерены neutral/raise/curl, hand close-up и новая
r2 baseline с теми же camera/light/samples. Сравнение показывает улучшение
рукавов и neutral позы; крупный план обнаруживает плоскую ладонь и недостаток
wrist/cuff сопряжения. Голова/волосы заметно уступают исходному референсу.
Не объявляем finished beauty pass. Файл review явно содержит `approved=false`.

**Проверки/учёт:** 203 unit/process tests (70+51+35+19+28) локально passed;
remote Actions не запускался. 31 задача: 8 done, 1 in_progress, 22 planned.
Evidence добавлено к planned RIG-01/QA-01, без закрытия зависимостей или G3.
184-test receipt архивирован как `body-r2-verification-2026-11-03.json`.
Подробности и воспроизведение — документ 41; актуальный receipt — verification.

**Далее:** форма ладони/wrist-cuff, художественная переработка головы/волос,
face/phoneme pipeline и живая актёрская подача. Ни 8/12/40 s scenes, ни
профессионально завершённая внешность не заявляются достигнутыми.

## ADR-012 · R4: native look-development не подменяет приёмку

**Дата:** 2026-11-03 · **статус:** реализован отдельный still-review с blockers.

Новый рецепт головы/волос/кистей сохраняет R1–R3. Не выдаём набор простых
геометрических форм и прохождение схем за профессиональный художественный
результат. Показываем 5 реальных Cycles stills, сохраняем исходные PNG вне
временных cache/out, явно отделяем layout от native кадров. Удаляем старые
неподдерживаемые jaw/blink bindings вместо имитации готового face rig.

Повторяем native stress suite на изменённой геометрии. Выявлен **регресс**:
15/17 static и 56/72 intermediate frames, area ratio до 7.452 при допуске 6.
Coordinator exit 1 сохранён, threshold не ослаблен. Результат R3 не переносим
на R4; последняя остаётся вне production swap и animation acceptance.

## Итерация 2026-11-03 · R4: кадры вместо обещания готового качества

Переработаны профиль/поверхность лица, орбитальная область, уши, fitted eyes,
единая масса волос с 480 ribbons, борода, palm pads/shafts и wrist extension.
После просмотренных неудачных вариантов исправлены террасы, парящие пряди
и избыточное выступание глаз. Сделаны 5 чистых 1024×1024/48-sample Cycles
кадров и подписанный review-board. Все исходные PNG архивированы в
`studio/reviews/dad-r4`; никакой AI-дорисовки/ретуши.

**Самопроверка отрицательная:** до канона/киноуровня далеко, сохраняются
helmet hair, искусственные веки, прямоугольная ладонь/трубчатые пальцы,
восковые материалы и недоработка одежды. Рот/face rig не готовы. Native strain
regression обнаружен и записан отдельно; 222 unit tests не отменяют failed
native gates или visual review. ART/RIG/QA и пользовательская приёмка открыты.
Receipt R3/203 tests сохранён отдельно; remote CI/commit/push не выполнялись.
Подробности, воспроизведение и следующий шаг — документ 42.

## Итерация 2026-11-03 · Публикация и исправление thumb-web regression R5

По прямому указанию пользователя работа публикуется небольшими проверяемыми
коммитами постоянно, а не накапливается только в sandbox. Опубликованы
`5c120fc` / `b66f665` (накопленный pipeline/кадры/история пилота), затем
`1535b22` (локализация и честно отклонённый spatial-field experiment).
Обе лёгкие GitHub Actions проверки прошли на b66f665 и 1535b22; они не
запускают native Blender. Правило закреплено в AGENTS.md.

Нативно локализован failing triangle у thumb/palm transition на обеих кистях.
Первый эксперимент уменьшил max stretch, но внёс сжатие и отвергнут. Второй
сглаживает исходные weights по реальным rest edges, оставляя geometry,
topology, probe IDs, остальные пальцы и anchors неизменными. R5 прошёл все
17 static poses и все 72 intermediate frames без изменения limits/fixture.
Animated max area 1.95412, max edge 2.05797; веса исправлены у 619 vertices/hand.

235 unit/process tests passed; отрендерены и просмотрены два новых native
1024×1024 hand stills. Artistic/anatomy approval=false: видимое улучшение
локальное, прямоугольная ладонь/трубчатые пальцы остались. Это техническое
исправление, не законченная модель. Production default/gates не переключались.
Подробности и воспроизведение — docs43; R4 failures/recipes сохранены.

## Итерация 2026-11-03 · Rain v3 → мама, реальная адаптация вместо нового блокинга

Пользователь разрешил bounded experiment на готовой Rain: сначала skin/body/
face, одежда позже. Официальный zip/.blend получен в GitHub native worker с
точным hash verification; direct sandbox download не работает. Адаптация не
использует чужой изменённый GLB или сгенерированное изображение.

Checkpoint b2b6c25 → source 5f67176 → actual A1 f92f578/ce24c5a → calibrated A2
bc6465a/0976a86. Все опубликованы на прежней ветке PR3. A1 ошибочная нейтральная
«улыбка» сохранена как failed/partial evidence; A2 действительно управляет
исходными ACT controls через оригинальные drivers, не прямой заменой key values.
Rest-space форма и все исходные shape keys редактируются согласованно,
rig rest/weights и топология не переписываются, источник не заменён.

Новый отдельный workflow **действительно** рендерит Blender; прежние два
лёгких CI всё ещё не являются native render tests. A2 source/candidate expressions
и full/face/three-quarter PNG, editable packed .blend artifact сохранены.
256 local tests passed; native rest signature/topology unchanged/new invalid=0.
Один original spine driver invalid сохраняется, full animation pass не проведён.

Art/likeness/acting acceptance=false: лицо всё ещё Rain; улучшения кожи/талии/
щек/носа/бровей — первый проход. Closed-eye lashes/lid surface выглядят плохо
даже в paired source setup, улыбка сдержанная. Следующий шаг — authored face
refinement и совместная работа upper/lower lids с native intermediate checks;
гардероб и canonical defaults пока не меняем. Подробности/ссылки — документ44.
