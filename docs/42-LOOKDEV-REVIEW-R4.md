# 42 · R4: форма, материалы и контрольные кадры

**2026-11-03 · `dad-body-rig@r4` · `art_status=unreviewed` · приёмка BLOCKED.**

Цель — не учебная демонстрация API, а выразительный семейный персонаж
киноуровня. **Эта версия цели ещё не достигла.** Ни новый renderer, ни число
тестов, ни более плотная сетка не являются подтверждением художественного
качества. R4 — отдельная ветвь look-development, не замена проверенному
техническому эксперименту R3 и не production deformation-ready asset.

## Что реально сделано

- Новые авторские формы `studio/authoring/lookdev.py`, native builder
  `studio/tools/build_dad_lookdev.py`. R1–R3 recipes не переписаны.
- Общая поверхность головы с носом, щеками и орбитальной областью, C1 profile
  без прежних горизонтальных террас. Изменены пропорции головы. Уши имеют
  углубление и ободок; глаза — отдельные sclera/iris/pupil и переход век к коже.
- В процессе просмотрены и отвергнуты варианты с плавающими толстыми
  «прядями», террасами головы и чрезмерно выступающими глазами. Уменьшена
  ширина белка, согласована поверхность радужки с белком и inner lid boundary.
- Непрерывная масса волос и 480 тонких геометрических ribbon-прядей; борода
  совмещает vertex tint общей поверхности и отдельные тонкие волокна.
  Это **не** полноценный production groom с симуляцией и LOD.
- Добавлены thenar/hypothenar объёмы, расширение пальцев и локальные подушки
  суставов. Кожа запястья продлена под манжету. После двух authoring
  Catmull–Clark уровней каждая кисть имеет 19 586 vertices / 19 584 quads,
  одну замкнутую компоненту и нормализованные веса. Tip-ring IDs сохранены.
  Это описание структуры, **не** положительная оценка анатомии.
- Сохранён body rig из 51 кости. Удалены неподдерживаемые `jaw.open` и два
  `eye.*.blink`: новый статический рот нельзя выдавать за готовую артикуляцию.
  Модель не имеет ротовой полости, зубов/языка, лицевого acting rig и lipsync.

## Реальные изображения

Пять чистых **native Blender 4.5 / Cycles** PNG: 1024×1024, 48 samples,
2 render threads, AgX. Просмотрены портрет, фронт, полный рост, раскрытая
кисть и сгибание. Без AI-дорисовки, ретуши, скрывающих недостатки overlays
или подмены кадров иллюстрацией. Картинка канона не изменена.

Постоянный небольшой архив находится **вне временных `.cache` и `out`**:

- [Обзорный лист](../studio/reviews/dad-r4/review-board.jpg).
- [Портрет ¾](../studio/reviews/dad-r4/hero.png).
- [Фронт](../studio/reviews/dad-r4/front.png).
- [Полный рост](../studio/reviews/dad-r4/full.png).
- [Раскрытая кисть](../studio/reviews/dad-r4/hand_open.png).
- [Сгибание пальцев](../studio/reviews/dad-r4/hand_curl.png).

Лист — только подписанный layout этих изображений: уменьшение для показа
и горизонтальная display-crop полного роста; фигура не обрезана. Все исходные
квадратные PNG сохранены без изменений. `studio/reviews/dad-r4/manifest.json`
содержит SHA256 оригиналов и листа. `dad-r4-render-report.json` хранит camera,
lighting, source blend SHA, renderer/script SHA, runtime и process reports.
Пять worker exits = 0; максимальный sampled process-group RSS ≈1361.1 MiB,
бюджет 2048 MiB / 300 s **на worker**. Это watchdog, не cgroup hard limit.

## Самопроверка по изображению — художественная приёмка НЕ пройдена

Сопоставление с неизменённым `studio/2p5d/dad/master-front-v2.png`:

| Область | Наблюдение на реальном изображении | Решение |
|---|---|---|
| Узнаваемость и стиль | Референс заметно живее и детальнее; форма лица, нос, веки и рисунок бороды ещё расходятся | Не принято |
| Силуэт волос | Вместо отдельных парящих деталей есть общая масса, но она всё ещё читается как жёсткая шапка, не как объёмный направленный quiff референса | Переработать |
| Лицо и взгляд | Выступание глаз уменьшено, однако переходы век и нижняя складка искусственны; рот — тонкая статическая линия | Не принято |
| Материалы | Есть radial iris, SSS/roughness и волокна; кожа восковая, борода местами штриховая, а не убедительный groom | Не принято |
| Ладонь и пальцы | Wrist/cuff связан визуально, но ладонь остаётся прямоугольной, пальцы трубчатыми, суставы при сгибании излишне сегментированы | Не принято |
| Полная фигура | Голова, массивная одежда и обувь пока дают общий mascot/prototype силуэт; одежде недостаёт структуры и деталей канона | Не принято |
| Современность | Cycles/AgX и layered materials подходят как инструменты; это не делает художественное решение современным или киношным автоматически | Не заявляется достигнутой |
| Актёрская готовность | Нет моргания, выражений, речи, teeth/tongue и полноценного facial rig | Не готово |

Таким образом, требование «не студенческая практическая работа» остаётся
открытым. Представленные кадры — честное свидетельство текущего состояния,
а не заявление о достижении этого уровня.

## Численные проверки и обнаруженная регрессия

**222 pure/process unit tests passed**: прежние 203 + 19 R4. Новые тесты
проверяют C1 профиля, topology/weights, сохранение tip IDs, зеркальность
геометрии (без ложного предположения о совпадении L/R vertex order), реальное
расширение shaft, boundary белка/века, положение iris на white surface и
внутри aperture, намеренно открытые groom ribbons, schema/provenance.
Никакого автоматического beauty/likeness score нет.

Отдельный версионированный `studio/tools/check_lookdev.py` проверяет **именно
новый native R4 blend**, а не переносит зелёный результат R3. Повторены
неизменённые R3 stress fixtures и limits: area ratio >0.025 / <6, edge ratio
<3, IK residual ≤5 mm. Проверяются evaluated surfaces, не только контроллеры.

| Проверка R4 | Результат | Что найдено |
|---|---|---|
| 17 статических поз | **15/17, FAILED** | R/L curl: max local area ratio **7.4490**, выше допуска 6 |
| 72 промежуточных кадра | **56/72, FAILED** | Frames 38–53: max local area ratio **7.4520** |
| Минимальная площадь / maximum edge, animated | 0.06062 / 2.71349 | Эти отдельные ограничения соблюдены; общий gate всё равно failed |
| IK, animated | max 0.07182 mm | Не компенсирует провал поверхности |
| Stationary contact probes | passed | Не проверка ходьбы, баланса или отсутствия столкновений |

Оба coordinator запуска честно возвращают **exit 1**. Worker exit 0 означает
только завершение измерения; итоговый quality status читается из JSON и
не подменяется process success. Отчёты: `dad-r4-extremes.json` и
`dad-r4-animated.json`. Не увеличивали допуск и не выдавали провал за pass.
**R4 не допускается к animation acceptance / production swap.** Место
максимального растяжения ещё требует локализации по конкретным faces;
по этому тесту нельзя честно утверждать, что это именно большой палец.

Геометрия головы/волос замкнута, groom cards намеренно открыты. Нет exhaustive
self/inter-object collision tests, клинической анатомической экспертизы,
face deformation suite, полного walking/cloth/acting acceptance. 222 unit tests
не закрывают эти пробелы. Remote GitHub Actions не запускался.

## Воспроизведение

Runtime восстанавливается по `studio/production/blender-requirements.lock`
и native lock; experimental ELF mirror требует явного opt-in (документ 38).
Это всё ещё не утверждённая production OS/runtime supply chain.

```bash
export LD_LIBRARY_PATH="$PWD/.cache/blender-native${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
.cache/blender-venv/bin/python studio/tools/build_dad_lookdev.py
.cache/blender-venv/bin/python studio/tools/render_lookdev.py \
  --size 1024 --samples 48 --record studio/production/dad-r4-render-report.json
.cache/blender-venv/bin/python studio/tools/make_lookdev_review.py
# Следующие две команды в текущей версии ожидаемо дают exit 1:
.cache/blender-venv/bin/python studio/tools/check_lookdev.py
.cache/blender-venv/bin/python studio/tools/check_lookdev.py \
  --animation --output studio/production/dad-r4-animated.json
.cache/blender-venv/bin/python -m unittest studio.tests.test_pipeline \
  studio.tests.test_package_pipeline studio.tests.test_rig_pipeline \
  studio.tests.test_refinement_pipeline studio.tests.test_lookdev_pipeline \
  studio.tests.test_production_status -q
```

Generated blend/cache остаются в `studio/out/dad-lookdev-r4`; rebuild может
дать другой binary SHA. Исторический render receipt не переписывают, чтобы
он притворялся результатом нового binary. При новом rebuild для новой
приёмки нужно обновить package snapshot и заново получить render/audit receipts.

## Следующий шаг, без увеличения длительности

1. Локализовать failing faces и исправить cage/skin weights/correctives кисти
   под те же static + intermediate poses; не подбирать более мягкий limit.
2. Существенно переделать ладонь/webbing/суставы, а не только повышать subdivision.
3. Переработать глаза/веки, facial volumes и силуэт groom по канону; затем
   рот с полостью и артикуляцией. Повторить front/¾/profile review без ретуши.
4. Лишь после отдельной художественной приёмки и зелёного native regression
   переходить к facial acting и контрольной анимации.

ART-02/RIG-01/QA-01 и production gates остаются открыты. Receipt R3 с 203
тестами сохранён отдельно как `body-r3-verification-2026-11-03.json`.
