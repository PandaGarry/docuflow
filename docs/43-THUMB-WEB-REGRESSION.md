# 43 · Локализация регрессии кисти и ход исправления

**2026-11-03 · рабочая итерация; не художественная приёмка.**

## Публикация

Накопленный код, пять PNG и отрицательный R4 review опубликованы в текущую
ветку `arena/4c8ed03c-docuflow`, PR #3. Коммит `5c120fc`, merge с ранее
опубликованными коммитами пилота `b66f665`; force-push не использовался.
На `b66f665` оба GitHub Actions checks прошли: contract/process tests и
planning tests. Это **не** запуск Blender и не artistic acceptance.
При проверке чистого checkout исправлена ошибочная зависимость одного pure
contract test от генерируемого .blend: runtime file verification не отключалась,
source provenance по-прежнему проверяется отдельным unit test.

## Что локализовано

`check_lookdev.py` теперь сохраняет худший triangle, исходные/деформированные
world coordinates, площадь и реальные vertex-group weights для каждой кисти.
Добавлен `--inputs` для отдельных revision fixtures; старый R3 checker неизменён.

Новый запуск на восстановленном R4 воспроизводит **15/17 FAILED**. Дефект
локализован **у перехода ладони в основание большого пальца**, симметрично:
R triangle 33385 / vertices 1045, 9071, 13955; L triangle 33248.
Rest triangle area ≈1.9883e−7 m², posed ≈1.4811e−6 m², ratio ≈7.449.
Два близких по расположению vertices имеют существенно разные thumb weights,
а два иных — одинаковые. После изменения формы thenar/palm исходное cage
interpolation не обязательно даёт гладкое поле влияний в пространстве.
Это проверяемая гипотеза механизма растяжения, не доказательство всей анатомии.

Полные данные: `studio/production/dad-r4-localized-extremes.json`.
Результаты документа 42 и прежние receipts не переписаны.

## Первый эксперимент R5 — отклонён

Отдельный `refined_hands.py` и `build_dad_handfix.py` сохраняют геометрию,
топологию, tip IDs, R4 материалы и body rig. Изменяются только thumb/hand weights.
Простое пространственное поле axial onset + radial falloff уменьшило max area
ratio до ~2.165, **но** внесло сжатие до ~0.00822 и edge stretch ~3.03859.
То есть результат всё ещё **FAILED**, новый дефект не скрывается улучшением
одного показателя. Trial report и package сохранены в `production/experiments`.
Лимиты и позы не изменены. Этот эксперимент не является принятым исправлением.

Далее проверяется геометрически взвешенное сглаживание исходного поля на
mesh adjacency вместо замены всего thenar field. Обязательны повторные 17
poses, все 72 промежуточных кадра и осмотр нового native hand close-up.
Киноуровень, anatomy/likeness/face-rig и production swap остаются непринятыми.

## Второй эксперимент — техническая регрессия исправлена

Вместо пространственной замены поля сглажено **исходное** thumb/hand поле
на реальной mesh adjacency: inverse-square edge conductance, 48 Jacobi steps
с relaxation 0.5. Полные hand/thumb anchors закреплены, прочие пальцы и
forearm influences не меняются. Изменены веса 619 из 19 586 vertices каждой
кисти (>1e−6). Ни координаты, ни faces, ни tip IDs не изменены. Первый
отклонённый вариант доступен в коммите `1535b22` и experimental receipts.

| Проверка | R4 | R5 после сглаживания |
|---|---:|---:|
| Статические позы | 15/17 FAILED | **17/17 PASSED** |
| Промежуточные кадры | 56/72 FAILED | **72/72 PASSED** |
| Static max area ratio, весь проверяемый body subset | 7.4490 | **3.17198** |
| Animated max area ratio | 7.4520 | **1.95412** |
| Animated min area ratio | 0.06062 | **0.06062** |
| Animated max edge ratio | 2.71349 | **2.05797** |

Area >0.025/<6, edge <3, IK ≤5 mm — прежние limits. Сохранились все исходные
tracks, keys, contacts, finger checks; изменены только fixture revision IDs.
Coordinator exits = 0. `dad-r5-extremes.json`, `dad-r5-animated.json` включают
actual native evaluated geometry, triangle diagnostics, binary/checker SHA,
weight normalization и process watchdog measurements. Production default
не переключался на R5 автоматически.

13 новых regression tests проверяют неизменность geometry/topology/tip IDs,
anchors и остальных пальцев, локальность, нормализацию, mirror moments,
детерминизм, конфигурацию solver, bundle/provenance, сохранность motion fixture
и привязку passed receipts к проверенному blend/checker. Вместе **235 unit
и process tests passed**. Эти pure tests не запускают Blender в GitHub Actions:
native измерения действительно выполнены отдельно в рабочей среде.

## Новые реальные кадры и границы результата

Отрендерены и просмотрены два новых Cycles/AgX кадра 1024×1024, 48 samples,
с **теми же** camera/light/settings, что и R4 hand views:

- [Раскрытая кисть R5](../studio/reviews/dad-r5/hand_open.png).
- [Сгибание R5](../studio/reviews/dad-r5/hand_curl.png).

Чистые PNG без дорисовки/ретуши сохранены вне cache/out, hashes — в
`studio/reviews/dad-r5/manifest.json`; renderer/process — `dad-r5-render-report.json`.
**Внешняя форма почти не изменилась:** исправление локальное и весовое.
По этим кадрам нельзя заявлять художественный скачок. Прямоугольная ладонь,
трубчатые пальцы и сегментированные суставы остаются; self-review
`dad-r5-visual-review.json` имеет `approved=false`.

Это закрывает **конкретный технический regression**, не anatomical/beauty,
likeness, collision, walking/cloth или полный rig/acting gate. Следующая
крупная задача — существенная перестройка ладони/webbing/суставов и затем
face/groom, с сохранением этого native regression как обязательной проверки.

```bash
export LD_LIBRARY_PATH="$PWD/.cache/blender-native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.cache/blender-venv/bin/python studio/tools/build_dad_handfix.py
.cache/blender-venv/bin/python studio/tools/check_lookdev.py \
  --package studio/out/dad-handfix-r5/package.json \
  --inputs studio/production/dad-handfix --output studio/production/dad-r5-extremes.json
.cache/blender-venv/bin/python studio/tools/check_lookdev.py \
  --package studio/out/dad-handfix-r5/package.json --inputs studio/production/dad-handfix \
  --animation --output studio/production/dad-r5-animated.json
.cache/blender-venv/bin/python studio/tools/render_lookdev.py \
  --package studio/out/dad-handfix-r5/package.json --output studio/out/dad-r5-review \
  --views hand_open hand_curl --size 1024 --samples 48 \
  --record studio/production/dad-r5-render-report.json
```

При повторном rebuild не подменять исторические SHA новыми: заново получать
согласованные package snapshot, native reports и frames. Generated blends не
публикуются в Git; исходники, кадры и JSON evidence публикуются. Плановые
production ART/RIG/QA gates остаются открытыми.
