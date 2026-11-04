# 40 · Body-прототип r2 и измерение контакта

> Исторический r2-срез. Дальнейшая переработка кистей, плеч/локтей и
> visual review — [документ 41](41-DEFORMATION-REVIEW-R3.md). Receipt 184
> tests сохранён в `body-r2-verification-2026-11-03.json`; актуальный общий
> результат — `verification.json`. r2 recipes и producer hashes сохранены.


**Дата:** 2026-11-03. **Область:** технический прототип `dad-body-rig@r2`,
`art_status=unreviewed`. Не утверждённые likeness, походка или production rig.
Канонические картинки семьи не изменены.

## Что реализовано

- Отдельная recipe `studio/tools/build_dad_rig.py`. Предыдущая
  `build_dad_blockout.py` не переписана: она даёт исходную голову/лицо,
  затем r2 заменяет одежду, ноги, кисти и волосы. Manifest фиксирует SHA
  обеих recipes и чистого модуля геометрии `studio/authoring/mesh.py`.
- Свитер — одна индексированная замкнутая поверхность с вшитыми рукавами,
  а не пересекающиеся torso/shoulder/sleeve шары. 746 вершин, 708 faces,
  99.44% quads. Брюки — одна поверхность с общими crotch edges: 499/467,
  99.36% quads. Нет неиспользуемых вершин и edges с incidence, отличной от 2.
  Это проверка связности/рёбер, **не** сертификат отсутствия self-intersections
  или пригодности всех деформаций. Normals пересчитаны при authoring.
- 49 костей: pelvis/spine/chest/neck/head, ключицы, руки/кисти, бёдра/голени/
  стопы и по три сустава на каждом из пяти пальцев обеих рук. Ноги —
  non-stretch two-bone IK с knee poles; стопа копирует мировую ориентацию
  независимой цели. Кисти/пальцы имеют настоящие `POSE_ROTATION` bindings,
  а не вращение empty вместе с неподвижной ладонью.
- Armature skinning, normalised weights; свитер/брюки subdivide level 1.
  У измеряемых обуви/кистей нет topology-changing modifiers. 0 unweighted
  vertices; максимальная погрешность суммы весов — 2.98e-8.
- Кисть пока состоит из **шести замкнутых пересекающихся поверхностей**:
  ладонь и пять сегментированных пальцев. Это не seamless final hand mesh.
  Ногти, ладонные складки, корректирующие формы и grip/prop collision ещё нет.

Есть pelvis/spine/neck controls, но наличие костей не означает проверенный
IK/FK switch, heel/toe roll, twist redistribution, shoulder correctives или
production extreme-pose suite. Плечи, причёска и лицо остаются грубым блокингом.

## Короткий motion fixture

`studio/tools/build_body_test.py` детерминированно авторит
`studio/production/dad-rig/{project,shot}.json`: 72 кадра, 24 fps, 3 s,
640×360, 6 samples + denoise, два render threads, chunks по 4 кадра,
1536 MiB / 180 s на worker. Камера показывает обе стопы и тело без монтажа.

Корпус смещается влево/вниз, правая нога делает короткий шаг вперёд на
20 cm; затем корпус смещается вправо и левая нога подтягивается. Вторая
половина проверяет сгибание и раскрытие всех пяти пальцев правой руки.
Ключи содержат sampled smoothstep easing, сохранённые в общем linear IR.
Это специально медленный тест IK/контакта, **не** принятая походка.

Stance intervals — half-open, в абсолютных кадрах:

| Sole probe | Stance |
|---|---|
| L | [0, 49), [61, 72) |
| R | [0, 13), [37, 72) |

В этой пробе подошва плоская во всей stance. Здесь нет heel-strike/toe-off
фаз. Физическая устойчивость, распределение веса, центр масс и силы
контакта **не** вычисляются. Корпусное смещение не объявляется доказательством
динамического баланса. Ни gait synthesis, ни foot collision solver не добавлены.

## Измерения, а не координаты контроллеров

Добавлены optional-поля строгих v2 preview contracts:

- package: `contact_probes`, `fingertip_probes`, `provenance.dependencies`;
- shot: `contacts`, `finger_checks`;
- project: optional orthographic `camera` position/target/scale.

Старый r1 input остаётся допустимым. Неизвестные поля, повторные probe IDs,
индексы вершин, отсутствующие references, stance вне диапазона/overlap и
неверный SHA зависимости отклоняются. Bind запрещает меняющие topology
modifiers на измеряемых объектах. Это всё ещё `rig_preview`, не полный
универсальный rig/approval schema.

`backends/geometry_probes.py` читает вершины **evaluated mesh** после
armature/IK. Для обуви сохраняет четыре world-space точки подошвы,
для пальца — центр tip-ring в локальной системе **реально posed hand bone**.
Root motion или вращение запястья сами по себе не дают finger articulation.
`kinematics.py` проверяет:

1. полное frame coverage;
2. горизонтальное перемещение **каждой** sole point от начала её stance
   (не только centroid: yaw-slip тоже ловится), допуск 5 mm;
3. ошибку высоты всех sole points во stance, допуск 3 mm;
4. penetration во всех кадрах, включая swing, допуск 2 mm;
5. span каждого запрошенного fingertip в hand-local системе, минимум 25 mm.

Дополнительно измеряются IK tail-to-target residual (максимум 5 mm) и
relative bone-length error (максимум 0.001). Failed motion checks не дают
создать completed manifest. Узкие численные допуски не заменяют G3 review.

### Реальные найденные ошибки и негативные пробы

1. В первой версии loft-свитера после удаления shoulder patches оставались
   шесть orphan vertices. Честный component count был 7. Добавлен compact/
   remap vertices+weights; теперь component count = 1, тест запрещает orphan.
2. Первая native pose-проба проходила IK residual, но sole points скользили
   на **134.6 mm**, ошибка высоты была **40.0 mm**. Skinned objects не
   наследовали object translation рига. Исправлено object-parenting с
   сохранением rest matrices. Исходный отказ отдельно записан в
   `dad-rig-parenting-regression.json`, не выдан за успешный текущий результат.
3. Реальный bpy negative fixture оставляет root/wrist/foot/head animation,
   но замораживает все finger curves. Finger span падает до <0.001 mm;
   contact checks проходят, finger checks правильно отклоняются (exit 1).
   Receipt — `dad-rig-integration.json`.
4. Ещё один **реальный 4-frame render** намеренно объявляет поднятую правую
   стопу stance. Worker/raster/encode завершаются, но geometry gate даёт
   ожидаемый exit 1 и не создаёт completed manifest. Это проверка отказа
   всего coordinator, не только standalone pose checker. Receipt там же.

### Actual pose evaluation и native replay

72 кадра действительно вычислены в bpy 4.5.0, не синтетические метрики:

| Измерение | Результат |
|---|---:|
| Sole-point stance drift | 0.00433 mm |
| Ground error / maximum sole penetration | 0.02997 mm |
| Stance samples (foot × frame) | 108 |
| Maximum IK residual | 0.04498 mm |
| Maximum relative bone-length error | 3.502e-5 |
| Right finger tip span, hand-local | 106.47–138.31 mm |

`dad-rig-pose-report.json` содержит все измерения direct IR application.
`dad-rig-native-replay.json` отдельно повторяет все 72 кадра после открытия
экспортированного `preview-scene.blend`: только `scene.frame_set`, **без**
нашего `apply`. Это подтверждает воспроизведение сохранённых native F-curves,
а не только ручное применение control values. Обе пробы — **не рендер**.

## Фактический видеорендер и resume

Завершён job `589b03020c41fc58074be9fdb3502ff2aca44fbf045341d154bd0e265ee89c9e`:
72 native кадра, 640×360, 24 fps, 3 s, silent H.264 MP4 **91 486 bytes**.
Файл: `studio/out/dad-rig-preview/<job_id>/dad-preview.mp4`.
Все кадры полностью декодированы с проверкой dimensions/PTS/timebase.

18 разных worker PID; намеренная пауза после первого chunk (exit 75), затем
1 reused + 17 новых chunks, успешный exit 0. Повторный completed-cache
resume проверил весь manifest без рендера. Peak worker/group RSS —
657 858 560 bytes (~627.4 MiB); сумма worker wall time — 405.1877 s,
wall продолжения — 384.1924 s (не включает первый paused chunk).
Эти цифры нельзя напрямую сравнивать с r1: другие resolution/samples/geometry.

**Все rendered geometry measurements совпали** с отдельными direct IR и
native-key replay отчётами. Persisted evidence: `dad-rig-preview-report.json`,
`dad-rig-preview-manifest.json`, `dad-rig-integration.json` в
`studio/production/`. Full manifest скопирован из ignored cache в source tree.
Осмотрены реальные кадры 0/24/50: обе стопы видны, одна поднимается,
колени сгибаются, правая кисть закрывается. Плечи угловаты, сгибы одежды,
волосы и лицо требуют художественной переработки. Технический pass этого
не исправляет и не делает движение естественной утверждённой походкой.

## Пересборка

Runtime и ограничения экспериментального native mirror описаны в документах
38–39. Это не официально одобренный production OS image.

```bash
export LD_LIBRARY_PATH="$PWD/.cache/blender-native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.cache/blender-venv/bin/python studio/tools/build_dad_rig.py
.cache/blender-venv/bin/python studio/tools/build_body_test.py
.cache/blender-venv/bin/python studio/tools/check_dad_rig.py
.cache/blender-venv/bin/python -m studio.pipeline.render_package \
  --inputs studio/production/dad-rig \
  --package studio/out/dad-rig-r2/package.json \
  --output studio/out/dad-rig-preview --native-dir .cache/blender-native \
  --record studio/production/dad-rig-preview-report.json
# Для намеренной паузы добавить --max-new-chunks 1 (exit 75).
# Для продолжения/проверки готового cache добавить --resume.
```

Изменение pipeline/schema/source или повторная авторская сборка может менять
SHA и job identity; старая завершённая папка не перезаписывается. Рендеры и
`.blend` — производные в ignored `studio/out`, receipts/recipes — в Git.

## Проверки и состояние задач

Добавлены **35 pure tests** в `test_rig_pipeline.py`: indexed geometry,
weights, probe contracts, actual sliding/rotation/hover/penetration errors,
local finger gate и negative cases. Они не запускают bpy, не подменяют
реальное видео. CI path filters дополнены authoring/fixture/test paths;
удалённый Actions в этой итерации не запускался.

Вместе локально прошли **184 теста**: 70 v1 + 51 external/process + 35 rig +
28 tracker. В tracker закрыт только узкий **RIG-00** данного прототипа.
31 задача: 8 done, 1 in_progress (PIPE-01), 22 planned. Предыдущий receipt
149 tests сохранён как `external-package-verification-2026-11-03.json`;
текущая итоговая запись — `verification.json`.
ART-02, RIG-01, MOT-01 и полный G3 не объявляются готовыми: нужны likeness
review, нормальная hand/shoulder topology, extremes/correctives и убедительная
походка. Мимика, артикуляция по аудио и сцены 8/12/40 секунд остаются впереди.
