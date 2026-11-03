# 36 · Живой чек-лист производства

> Сгенерировано из `studio/production/plan.json`. Не редактировать вручную.
> Команда: `python3 studio/tools/production_status.py checklist --write`.

**Дата состояния:** 2026-11-03 · **цель:** персонажная анимация в стиле B; готовность подтверждается контрольными сценами

Всего задач: **31**. Выполнено: **8**; в работе: **1**; на проверке: **0**; с блокером: **0**; запланировано: **22**.

**Важно:** выполненные задачи документации/учёта не означают готовую 3D-анимацию. Учёт задач не заменяет художественную приёмку шлюза.

**Следующая приоритетная задача: PIPE-01.**

План: [33](33-PRODUCTION-PLAN.md) · архитектура: [34](34-ENGINE-ARCHITECTURE.md) · критерии: [35](35-QUALITY-GATES.md) · решения: [37](37-DECISION-LOG.md).

## Состояние шлюзов

| Шлюз | Задачи done | Состояние учёта |
|---|---:|---|
| G0 · План и стартовый срез | 5/5 | задачи закрыты; см. evidence |
| G1 · Среда и backend | 2/6 | не закрыт |
| G2 · Канон и модель | 0/3 | не закрыт |
| G3 · Тело и контакты | 1/4 | не закрыт |
| G4 · Лицо | 0/2 | не закрыт |
| G5 · Артикуляция по аудио | 0/4 | не закрыт |
| G6 · Соло-срез | 0/1 | не закрыт |
| G7 · Два героя | 0/2 | не закрыт |
| G8 · Серия и выпуск | 0/4 | не закрыт |

## P0 · План, среда и инфраструктура

- [x] **DOC-01 — Аудит и последовательный план реализации**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G0.
  - Зависимости: нет.
  - Результат: docs/33-PRODUCTION-PLAN.md.
  - Готово когда: отделены имеющиеся функции от планируемых; у этапов есть зависимости, выходы и условия остановки.
  - Evidence: [docs/33-PRODUCTION-PLAN.md](../docs/33-PRODUCTION-PLAN.md).
- [x] **DOC-02 — Архитектура и границы модулей**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G0.
  - Зависимости: DOC-01.
  - Результат: docs/34-ENGINE-ARCHITECTURE.md.
  - Готово когда: определены DCC adapter, данные, время, координаты и invalidation; проектируемые модули не выданы за готовые.
  - Evidence: [docs/34-ENGINE-ARCHITECTURE.md](../docs/34-ENGINE-ARCHITECTURE.md).
- [x] **DOC-03 — Измеримые шлюзы и художественная приёмка**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G0.
  - Зависимости: DOC-02.
  - Результат: docs/35-QUALITY-GATES.md.
  - Готово когда: разделены технические допуски и решение пользователя; определены тестовые реплики, опоры и контрольные сцены.
  - Evidence: [docs/35-QUALITY-GATES.md](../docs/35-QUALITY-GATES.md).
- [x] **OPS-01 — Единый tracker, валидатор и регрессионные тесты**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G0.
  - Зависимости: DOC-03.
  - Результат: studio/production/plan.json; studio/tools/production_status.py; studio/tests/test_production_status.py; docs/36-PRODUCTION-TRACKER.md; .github/workflows/production-plan.yml.
  - Готово когда: проверены DAG, evidence, статусы и защита от ложного approval; Markdown воспроизводим из JSON без ручных статусов.
  - Evidence: [studio/tools/production_status.py](../studio/tools/production_status.py), [studio/tests/test_production_status.py](../studio/tests/test_production_status.py), [studio/production/verification.json](../studio/production/verification.json), [.github/workflows/production-plan.yml](../.github/workflows/production-plan.yml).
- [x] **ENV-01 — Снимок фактически доступной среды**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G0.
  - Зависимости: DOC-02.
  - Результат: studio/production/environment.json.
  - Готово когда: зафиксированы обнаруженные бинарники и Python-пакеты; непроверенные GPU и headless runtime отмечены как not_probed/not_run.
  - Evidence: [studio/production/environment.json](../studio/production/environment.json).
- [x] **ENV-02 — Headless Blender и FFmpeg smoke test**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G1.
  - Зависимости: ENV-01.
  - Результат: runtime lock и environment report; 24 кадра 1080p и полностью декодируемый MP4.
  - Готово когда: реально проверены IK, shape key, lighting и frame export; сохранены версии, exit codes, время и peak RAM.
  - Evidence: [studio/production/blender-smoke-report.json](../studio/production/blender-smoke-report.json), [studio/production/blender-requirements.lock](../studio/production/blender-requirements.lock), [studio/production/blender-hardware-inventory.json](../studio/production/blender-hardware-inventory.json), [studio/production/blender-negative-probes.json](../studio/production/blender-negative-probes.json), [studio/production/blender-scene-reload.json](../studio/production/blender-scene-reload.json), [docs/38-BLENDER-MVP.md](../docs/38-BLENDER-MVP.md).
- [ ] **ENV-04 — Подготовить проверяемое production-окружение без mirror fallback**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G1.
  - Зависимости: ENV-02.
  - Результат: поддерживаемая OS/base image с официальными системными зависимостями; проверенные patch versions, licenses/security review и чистый повторный smoke test.
  - Готово когда: native libraries получены из официального проверяемого источника, а не из экспериментального distro mirror; на чистой среде повторены реальные 24 кадра и decode без sandbox fallback; version pins усилены проверкой wheel/image integrity; ограничения и результаты записаны; профилирована память на длинной последовательности; CPU/thread budget соответствует фактическому affinity, не числу запрошенных потоков.
- [ ] **PIPE-01 — Реализовать версионированные контракты**
  - Статус: **в работе**. Ответственность: агент. Шлюз: G1.
  - Зависимости: DOC-02.
  - Результат: schemas для project/asset/rig/speech/shot/render manifest; валидатор и негативные fixtures.
  - Готово когда: есть миграция или явный отказ несовместимой схемы; frame/sample timebase и оси проверены тестами; контракты поддерживают внешний production character/rig package, не только synthetic probe.
  - Evidence: [studio/pipeline/contracts.py](../studio/pipeline/contracts.py), [studio/tests/test_pipeline.py](../studio/tests/test_pipeline.py), [docs/38-BLENDER-MVP.md](../docs/38-BLENDER-MVP.md).
- [ ] **PIPE-02 — Реальный Blender render adapter**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G1.
  - Зависимости: ENV-02, PIPE-01.
  - Результат: backend subprocess adapter; тестовая scene/frame sequence.
  - Готово когда: отсутствующий канал и сбой renderer не скрываются; frame count, color config и hashes входят в manifest; внешняя модель/риг загружаются из asset package; probe не подставляется вместо персонажа; для длинных jobs есть ограничение RSS и безопасное разбиение/restart worker; 24-кадровый smoke не считается доказательством стабильности 960 кадров.
  - Evidence: [studio/pipeline/run_probe.py](../studio/pipeline/run_probe.py), [studio/pipeline/backends/blender_worker.py](../studio/pipeline/backends/blender_worker.py), [docs/38-BLENDER-MVP.md](../docs/38-BLENDER-MVP.md).
- [x] **PIPE-04 — Внешний 3D-preview: bounded workers и chunk-resume**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G1.
  - Зависимости: ENV-02, DOC-02.
  - Результат: версионированный внешний .blend package с hash/collection/bindings; ограниченные worker-процессы и проверяемые chunk checkpoints; нативный 48-кадровый preview неутверждённого блокинга.
  - Готово когда: реально отрендерен внешний пакет без процедурного fallback; настоящий Blender прерывается по низкому RSS budget; missing collection/control — явная ошибка; pause/resume сохраняет первый complete chunk без повторного рендера; corrupt cache отклоняется; полный MP4 декодирован, frame count/PTS/timebase/resolution совпадают; нет художественного approval и заявлений о походке/lipsync/production-ready модели.
  - Evidence: [studio/pipeline/packages.py](../studio/pipeline/packages.py), [studio/pipeline/resources.py](../studio/pipeline/resources.py), [studio/pipeline/render_package.py](../studio/pipeline/render_package.py), [studio/tests/test_package_pipeline.py](../studio/tests/test_package_pipeline.py), [studio/production/dad-package-integration.json](../studio/production/dad-package-integration.json), [docs/39-EXTERNAL-PACKAGES-AND-BOUNDED-WORKERS.md](../docs/39-EXTERNAL-PACKAGES-AND-BOUNDED-WORKERS.md), [studio/production/dad-preview-report.json](../studio/production/dad-preview-report.json), [studio/production/package-empty-log-regression.json](../studio/production/package-empty-log-regression.json), [studio/production/package-short-regression-report.json](../studio/production/package-short-regression-report.json), [studio/tools/build_dad_blockout.py](../studio/tools/build_dad_blockout.py), [studio/production/dad-preview-manifest.json](../studio/production/dad-preview-manifest.json).
- [ ] **QA-01 — Реализовать отчёты измерений и gate harness**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G1.
  - Зависимости: PIPE-01.
  - Результат: quality reports и тестовые fixtures; схема approval record.
  - Готово когда: вычисление slip и временных residuals проверено на искусственных ошибках; художественное одобрение не выводится из метрик.
  - Evidence: [studio/tools/check_body_extremes.py](../studio/tools/check_body_extremes.py), [studio/production/dad-r3-animated-strain.json](../studio/production/dad-r3-animated-strain.json), [studio/tests/test_refinement_pipeline.py](../studio/tests/test_refinement_pipeline.py), [docs/42-LOOKDEV-REVIEW-R4.md](../docs/42-LOOKDEV-REVIEW-R4.md), [studio/production/dad-r4-visual-review.json](../studio/production/dad-r4-visual-review.json), [docs/43-THUMB-WEB-REGRESSION.md](../docs/43-THUMB-WEB-REGRESSION.md), [studio/production/dad-r5-extremes.json](../studio/production/dad-r5-extremes.json), [studio/production/dad-r5-animated.json](../studio/production/dad-r5-animated.json).

## P1 · Канон, модели и риги

- [ ] **ART-01 — Утвердить единый канон семьи**
  - Статус: **запланировано**. Ответственность: производство ассетов + пользователь. Шлюз: G2.
  - Зависимости: DOC-01.
  - Результат: approved turnaround, пропорции и palette reference; approval record с revision.
  - Готово когда: внешность сопоставлена с пользовательскими референсами; пользователь принял конкретную версию.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
- [ ] **ART-02 — Создать deformation-ready модель папы**
  - Статус: **запланировано**. Ответственность: производство ассетов + пользователь. Шлюз: G2.
  - Зависимости: ART-01, ENV-02.
  - Результат: модель папы с материалами, глазами, ртом, зубами и языком; контрольные рендеры и asset manifest.
  - Готово когда: модель узнаваема в повороте и пригодна для рига; проверены topology, scale, скрытые поверхности и provenance.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
  - Evidence: [docs/42-LOOKDEV-REVIEW-R4.md](../docs/42-LOOKDEV-REVIEW-R4.md), [studio/production/dad-r4-visual-review.json](../studio/production/dad-r4-visual-review.json), [studio/reviews/dad-r4/manifest.json](../studio/reviews/dad-r4/manifest.json), [studio/production/dad-r5-visual-review.json](../studio/production/dad-r5-visual-review.json).
- [ ] **ART-03 — Собрать сцену и контактные поверхности**
  - Статус: **запланировано**. Ответственность: производство ассетов. Шлюз: G2.
  - Зависимости: ART-01, ENV-02.
  - Результат: гостиная, свет, пол и prop proxies; стандартные камеры тестов.
  - Готово когда: поверхности заданы в мировых единицах; свет и цвет воспроизводимы между планами.
- [x] **RIG-00 — Технический body-прототип r2: IK ног, пальцы и sole probes**
  - Статус: **выполнено**. Ответственность: агент. Шлюз: G3.
  - Зависимости: ENV-02, PIPE-04.
  - Результат: независимая r2 recipe, цельная одежда и 49-костный прототип; 3 s technical fixture, evaluated sole/fingertip reports и негативные проверки.
  - Готово когда: свитер/брюки — по одной замкнутой indexed surface; веса нормализованы; IK ног и сгибание всех пяти пальцев проверены на evaluated geometry; восстановление batched render и native-key replay воспроизводят short fixture; это не закрывает ART-02/RIG-01/MOT-01 или полную приёмку G3.
  - Evidence: [studio/production/dad-rig-pose-report.json](../studio/production/dad-rig-pose-report.json), [studio/production/dad-rig-integration.json](../studio/production/dad-rig-integration.json), [studio/tests/test_rig_pipeline.py](../studio/tests/test_rig_pipeline.py), [studio/tools/build_dad_rig.py](../studio/tools/build_dad_rig.py), [studio/production/dad-rig-model-audit.json](../studio/production/dad-rig-model-audit.json), [studio/production/dad-rig-native-replay.json](../studio/production/dad-rig-native-replay.json), [studio/production/dad-rig-preview-report.json](../studio/production/dad-rig-preview-report.json), [studio/production/dad-rig-preview-manifest.json](../studio/production/dad-rig-preview-manifest.json), [docs/40-BODY-RIG-AND-CONTACT-PROBES.md](../docs/40-BODY-RIG-AND-CONTACT-PROBES.md).
- [ ] **RIG-01 — Тело: IK/FK, пальцы, стопа и correctives**
  - Статус: **запланировано**. Ответственность: риг/анимация + агент. Шлюз: G3.
  - Зависимости: ART-02, PIPE-01.
  - Результат: body rig package и binding; extreme-pose suite.
  - Готово когда: нет сломанных плеч/коленей и отрыва одежды; контакты и длины костей проходят G3.
  - Evidence: [studio/tools/build_dad_refined.py](../studio/tools/build_dad_refined.py), [studio/production/dad-r3-model-audit.json](../studio/production/dad-r3-model-audit.json), [studio/production/dad-r3-extremes.json](../studio/production/dad-r3-extremes.json), [studio/production/dad-r3-visual-review.json](../studio/production/dad-r3-visual-review.json), [studio/production/dad-r4-extremes.json](../studio/production/dad-r4-extremes.json), [studio/production/dad-r4-animated.json](../studio/production/dad-r4-animated.json), [docs/43-THUMB-WEB-REGRESSION.md](../docs/43-THUMB-WEB-REGRESSION.md), [studio/production/dad-r5-extremes.json](../studio/production/dad-r5-extremes.json), [studio/production/dad-r5-animated.json](../studio/production/dad-r5-animated.json).
- [ ] **RIG-02 — Лицевой риг и артикуляционные формы**
  - Статус: **запланировано**. Ответственность: риг/анимация + агент. Шлюз: G4.
  - Зависимости: ART-02, PIPE-01.
  - Результат: face rig, viseme shapes и correctives; крупные планы тестовых сочетаний.
  - Готово когда: проверены смыкание глаз/губ и jaw/teeth; эмоция не ломает обязательные closures.

## P2 · Речь и актёрское движение

- [ ] **ENV-03 — Проверить русский forced aligner и права на модель**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G5.
  - Зависимости: ENV-01.
  - Результат: aligner/model compatibility report; проверенный phoneme inventory и fallback.
  - Готово когда: установленная версия и веса реально доступны и лицензии записаны; иначе выбран и явно обозначен ручной phone-alignment workflow.
- [ ] **AUD-01 — Утвердить голос и записать тестовые реплики**
  - Статус: **запланировано**. Ответственность: озвучка + пользователь. Шлюз: G5.
  - Зависимости: DOC-01.
  - Результат: три immutable dialogue take и точный transcript; speaker/take/checksum metadata.
  - Готово когда: достаточно closures и переходов для G5; голос папы выбран пользователем; старый narrator не переименован в папу.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
- [ ] **AUD-02 — Получить и проверить интервалы фонем**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G5.
  - Зависимости: AUD-01, ENV-03, PIPE-01.
  - Результат: phone spans в audio samples; ручные landmarks и ошибки выравнивания.
  - Готово когда: разметка относится к checksum финального дубля; ASR words и буквенные тайминги не выданы за phone alignment.
- [ ] **LIP-01 — Коартикуляция и привязка речи к лицу**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G5.
  - Зависимости: AUD-02, RIG-02.
  - Результат: speech curves и rig binding; front/3-4 артикуляционные тесты.
  - Готово когда: выполнены временные допуски G5; closures сохраняются при улыбке; нет дрожи зубов.
- [ ] **MOT-01 — Походка: старт, шаги, остановка и опоры**
  - Статус: **запланировано**. Ответственность: анимация + агент. Шлюз: G3.
  - Зависимости: RIG-01, ART-03, QA-01.
  - Результат: walk-start-stop clip и path/contact tracks; численный contact report.
  - Готово когда: виден перенос веса и обе ноги; slip измерен относительно поверхности, допуски G3 соблюдены.
- [ ] **ACT-01 — Жесты и контакт кисти с целью**
  - Статус: **запланировано**. Ответственность: анимация + агент. Шлюз: G3.
  - Зависимости: RIG-01, ART-03, QA-01.
  - Результат: point и touch gestures с фазами; contact targets и отчёт.
  - Готово когда: есть preparation, stroke, hold, recovery; движение руки непрерывно и контакт не проваливается в лицо.
- [ ] **FACE-01 — Взгляд, эмоции и реакция по смысловым beats**
  - Статус: **запланировано**. Ответственность: анимация + агент. Шлюз: G4.
  - Зависимости: RIG-02.
  - Результат: face performance clips; просмотр neutral-to-reaction.
  - Готово когда: нет бессмысленной случайной дрожи; эмоция, моргание и взгляд образуют читаемую реакцию.

## P3 · Контрольные сцены

- [ ] **SHOT-01 — Принять соло-срез с папой, 8 секунд**
  - Статус: **запланировано**. Ответственность: агент + анимация + пользователь. Шлюз: G6.
  - Зависимости: PIPE-02, QA-01, LIP-01, MOT-01, ACT-01, FACE-01.
  - Результат: 192 кадра: walk-stop-speak-gesture; QC и approval record.
  - Готово когда: пройден G6 на полном росте и крупном плане; пользователь принял кандидата; движения не скрыты монтажом.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
- [ ] **ART-04 — Модель и собственный риг сына для реакции**
  - Статус: **запланировано**. Ответственность: производство ассетов + пользователь. Шлюз: G7.
  - Зависимости: SHOT-01, ART-01.
  - Результат: son asset/face rig package; identity и reaction tests.
  - Готово когда: сохранены детские пропорции, не уменьшенная копия взрослого; пользователь принял внешность и реакцию.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
- [ ] **SHOT-02 — Принять двухгеройный срез, 12 секунд**
  - Статус: **запланировано**. Ответственность: агент + анимация + пользователь. Шлюз: G7.
  - Зависимости: SHOT-01, ART-04.
  - Результат: 288 кадров: папа действует, сын реагирует; eyeline/staging QC и approval.
  - Готово когда: пройден G7 с одним согласованным пространством; сын имеет реальную мимику, не статичную PNG-вставку.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.

## P4 · Серия и воспроизводимый выпуск

- [ ] **ART-05 — Довести маму и нужные действия всей семьи**
  - Статус: **запланировано**. Ответственность: производство ассетов + пользователь. Шлюз: G8.
  - Зависимости: SHOT-02, ART-01.
  - Результат: mom asset/body/face rig package; набор действий для выбранного сценария.
  - Готово когда: все действующие герои прошли применимые G2–G5; масштабы, характер походки и внешность приняты.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
- [ ] **PIPE-03 — Инкрементальная сборка и безопасный resume**
  - Статус: **запланировано**. Ответственность: агент. Шлюз: G8.
  - Зависимости: PIPE-02.
  - Результат: content-hash job/cache layer; resume/invalidation/partial-failure tests.
  - Готово когда: меняются только зависимые результаты; недостающие кадры не заменяются старыми, worker count проверен по памяти.
- [ ] **EP-01 — Произвести 40-секундную серию по этапам**
  - Статус: **запланировано**. Ответственность: производство + пользователь. Шлюз: G8.
  - Зависимости: SHOT-02, ART-05, PIPE-03.
  - Результат: script/dialogue/blocking/polish/light approvals; 960 кадров, mix, SRT и poster.
  - Готово когда: согласованы сценарий и этапы; нет batch на непринятом риге; пройден G8, включая художественные замечания.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.
- [ ] **REL-01 — Воспроизводимый выпуск и финальная приёмка**
  - Статус: **запланировано**. Ответственность: агент + пользователь. Шлюз: G8.
  - Зависимости: EP-01, QA-01.
  - Результат: delivery manifest, QC и release candidate; measured loudness/frame count и approval record.
  - Готово когда: чистая пересборка проверена на заявленном worker; пользователь принял финал; publish-ready не выставлен автоматически.
  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.

## Порядок обновления

1. Изменить JSON: статус, зависимости, blocker, acceptance и evidence.
2. Для done закрыть зависимости и приложить результат проверки; для visual approval — запись пользователя.
3. Запустить validate, тесты и checklist --write, затем checklist --check.
4. Добавить запись итерации в docs/37-DECISION-LOG.md: что сделано, что проверено, ограничения, следующий шаг.
5. Не отмечать готовность движка/сцены по одному наличию файлов или unit tests.
