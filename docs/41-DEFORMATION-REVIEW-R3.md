# 41 · R3: деформации и честный visual review

**2026-11-03 · `dad-body-rig@r3` · `art_status=unreviewed`.**
Ответ на запрос о профессиональной, красивой и современной работе: проверка
должна охватывать и численную корректность, и реальный внешний вид. Первое
не доказывает второе. Эта итерация улучшает тело и проверяет слабые места,
но **не объявляет персонажа красивым/готовым или соответствующим референсу**.

## Что действительно изменено

- R1/R2 recipes и канонические картинки не переписаны. Новый авторский
  рецепт — `studio/tools/build_dad_refined.py`, чистая геометрия —
  `studio/authoring/refined_body.py`. Source/dependency SHA входят в package.
- Вместо шести пересекающихся palm/finger оболочек — **одна замкнутая
  индексированная поверхность каждой кисти** с пятью вшитыми apertures.
  После одного authoring Catmull–Clark level: 4 898 vertices / 4 896 quads,
  connected components = 1, edge incidence = 2, orphan vertices = 0.
  Original tip-ring vertex IDs сохраняются. Runtime Subsurf на кисти не
  добавляется: geometry probes по-прежнему имеют точное соответствие.
- Исправлена зеркальная анатомия левой кисти: index теперь рядом с thumb,
  а не с противоположного края ладони. Перестроены rest finger bones.
- Исправлена neutral elbow pole plane. До калибровки elbow-to-rest error:
  R **57.54 mm**, L **185.43 mm**; после — около **0.00028 / 0.00030 mm**.
  Это исправление геометрии neutral bend, не только IK tail residual.
- Рукав использует C1 Hermite centerline вместо резкой смены tangent возле
  локтя. Исправлен заворот первой sleeve section внутрь torso aperture,
  локально сглажены плечи и расширен переход chest/clavicle/upper-arm weights.
- Добавлены **две elbow deformation helpers**: 51 кость вместо 49.
  Helper — дочерняя upper-arm кость с половинным world rotation blend к
  forearm; локально распределяет изгиб. Это не полный twist/PSD/corrective rig.
- Добавлены scalp patch под clumps и слабый procedural cloth bump. Они
  не считаются утверждённым hair sculpt или финальными материалами.

## Что нашла проверка

Первый вариант R3 достигал IK targets, но давал до **16.16×** растяжения
отдельных рёбер свитера и до 19.52× area ratio в fold pose. Отказ сохранён
в `dad-r3-initial-strain-failure.json`. Причины: почти совпадающие inner-elbow
rings в neutral, armpit fold-back и резкие weight transitions.

После статических исправлений 17 poses проходили, но проверка **всех
промежуточных кадров** выявила локальное схлопывание triangle area в движении.
Первый отказ сохранён в `dad-r3-initial-motion-failure.json`. Поэтому одних
neutral/extreme stills недостаточно. Добавлены elbow helpers и пространственная
Bezier-дуга wrist target: рука не тянется по прямой через чрезмерно сложенный локоть.
Пороговые значения при исправлениях **не ослаблялись**.

## Native QA, а не имитация результата

`studio/tools/check_body_extremes.py` реально вычисляет bpy evaluated meshes:

- 17 заданных static cases: neutral и по 8 для каждой стороны — reach,
  raise (`overhead` в имени fixture), abduction, elbow fold, wrist flexion/
  extension/deviation, finger curl;
- отдельно все 72 кадра authored reach/curl/recovery;
- фиксированная fan triangulation тех же polygons для сравнения area ratios;
- world edge lengths, finite/nondegenerate surfaces, стабильность topology;
- IK residual, bone lengths, evaluated sole probes и native weight sums.

Это **эвристические safety limits**, не физика ткани и не студийный G3:
minimum area ratio > 0.025, maximum < 6, edge stretch < 3,
IK residual ≤ 5 mm. Не доказаны отсутствие self-intersections, inter-object
collisions или нормальная пластика всех возможных поз. `subdivide()` — private
процедура для этих curated surfaces, не универсальный retopology/repair tool.

| Проверка | Static 17 | Animated 72 |
|---|---:|---:|
| Minimum area ratio | 0.12256 | 0.19442 |
| Maximum area ratio | 3.17198 | 2.40728 |
| Maximum edge stretch ratio | 2.93594 | 2.05797 |
| Maximum IK error | 0.02922 mm | 0.07182 mm |
| Native weight-sum error | 4.2841e-8 | 4.2841e-8 |

Отчёты: `studio/production/dad-r3-{extremes,animated-strain}.json`.

### Replay и негативная проба

Все 72 кадра direct IR, reopening exported native animation **без apply**
и measurements настоящих render workers совпали. Native replay:
`dad-r3-native-replay.json`; receipt — `dad-r3-integration.json`.

Реальная frozen-finger проба оставляет arm/wrist/head motion, но выключает
finger articulation. Она корректно даёт exit 1: contact проходит, finger
span не достигает 25 mm. Это исключает ложный pass только из-за перемещения руки.

В данном gesture fixture обе стопы неподвижны: 144 foot×frame stance samples,
нулевой drift. Это ожидаемый результат **неподвижных** ног, а не улучшенная
походка или доказательство динамического баланса.

## Реальный видеорендер

Job: `cde47ecbbf149bcea2c2b86843a867df8c985a6c3a7b34104c57f006b7540917`.

- **72 native frames, 640×360, 24 fps, 3 s**, silent H.264 MP4, **57 997 bytes**.
- `studio/out/dad-refined-preview/<job_id>/dad-preview.mp4`.
- 18 разных bounded worker PID, 18 новых chunks по 4 кадра, 6 samples +
  denoise, 2 threads. Peak worker/group RSS **666 009 600 bytes (~635.2 MiB)**.
- Coordinator wall 310.7236 s; сумма guarded worker process wall 309.6578 s.
  Это не benchmark против предыдущего переступа: другое движение/геометрия.
- Полностью декодированы 72 кадра; PTS/timebase/dimensions проверены.
  Completed-cache resume прошёл hash verification без повторного рендера.
- Full manifest сохранён вне cache: `dad-r3-preview-manifest.json`.
  Report — `dad-r3-preview-report.json`. Native runtime остаётся тем же
  экспериментальным окружением, не одобренным production image (см. 38–39).

## Visual review: что видно, а не что говорят тесты

Сделаны настоящие 768×576/16-sample renders: neutral, поднятая рука, curl,
отдельный крупный план кисти. `render_rig_review.py` заново отрендерил r2
с **той же камерой, светом, разрешением и samples**, что neutral r3.
В comparison только captions и размещение двух native renders — без
ретуши или подмены нарисованным персонажем.

- [До/после](../studio/out/dad-r3-review/comparison.png).
- [Крупный план кисти](../studio/out/dad-r3-review/hand-closeup.png).
- [Поднятая рука](../studio/out/dad-r3-review/R_overhead.png).

Receipt, hashes и замечания: `dad-r3-visual-review.json`, `approved=false`.
Осмотрены эти реальные stills и кадр 40 главного видеорендера. Просмотр
не объявляется полноценной покадровой художественной приёмкой всего ролика.

**Улучшилось:** neutral руки стали симметричнее; острый shoulder seam
сглажен; рука сгибается без прежнего сильного растяжения рукава; поверхность
кисти больше не состоит из шести пересекающихся shells.

**Не доведено:** ладонь слишком плоская/прямоугольная, сопряжение wrist/cuff
требует доработки, пальцевые позы выглядят схематично. Волосы, борода,
пропорции и пластика лица заметно уступают исходному reference. Face acting,
lipsync, secondary motion, collision-aware grip и естественная подача жеста
не реализованы. Это нельзя честно назвать finished beauty pass.

## Воспроизведение

```bash
export LD_LIBRARY_PATH="$PWD/.cache/blender-native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.cache/blender-venv/bin/python studio/tools/build_dad_refined.py
.cache/blender-venv/bin/python studio/tools/build_deformation_test.py
.cache/blender-venv/bin/python studio/tools/check_body_extremes.py
.cache/blender-venv/bin/python studio/tools/check_body_extremes.py \
  --animation --output studio/production/dad-r3-animated-strain.json
.cache/blender-venv/bin/python studio/tools/check_body_extremes.py \
  --render-dir studio/out/dad-r3-review
.cache/blender-venv/bin/python studio/tools/render_rig_review.py
.cache/blender-venv/bin/python -m studio.pipeline.render_package \
  --inputs studio/production/dad-refined \
  --package studio/out/dad-refined-r3/package.json \
  --output studio/out/dad-refined-preview --native-dir .cache/blender-native \
  --record studio/production/dad-r3-preview-report.json
# --resume для проверки/продолжения конкретной неизменённой job identity.
```

19 новых pure tests: connected topology, Catmull–Clark known cube step,
weight normalization, mirrored anatomy, stable probe indices, helper weights,
repeatable fixture/arc и сохранность provenance r2. Вместе **203 tests**:
70 v1 + 51 package/process + 35 r2 + 19 refinement + 28 tracker. Native QA
запускался отдельно; CI их не подменяет. Remote Actions не запускался.

31 задача: 8 done, 1 in_progress, 22 planned. Новый proof добавлен к
planned RIG-01 / QA-01 как prototype evidence; это **не** закрывает их
зависимости, полный G3, ART-02, MOT-01 или сцены 8/12/40 s.
Предыдущий 184-test receipt сохранён как `body-r2-verification-2026-11-03.json`.

**Далее:** исправить форму ладони и wrist/cuff, переработать голову/волосы
по канону, затем face/phoneme pipeline и более живую актёрскую анимацию.
Наращивать длительность на этом art-прототипе преждевременно.
