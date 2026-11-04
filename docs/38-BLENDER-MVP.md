# 38 · Первый исполнимый Blender-срез

**Дата:** 2026-11-02. **Область:** технический smoke pipeline, не готовый
генератор серий и не художественная модель семьи.

## Что действительно реализовано

В `studio/pipeline/` теперь есть работающий узкий вертикальный срез:

1. `contracts.py` — локальная JSON Schema 2020-12 валидация, версия 1,
   отказ от неизвестных версий/полей, проверка ссылок, путей, диапазонов,
   управляющих каналов и sample spans. Внешние schema URLs не загружаются.
2. `timeline.py` — покадровая линейная интерполяция семантических каналов,
   привязка к реальным объектам/shape keys; отсутствующий binding — ошибка.
3. `backends/rig_probe.py` — авторская процедурная диагностическая сцена:
   armature из двух костей, IK, одна сетка с весами, shape key челюсти,
   три area lights, материалы, камера и площадка. Это тестовый робот,
   **не папа, не сын и не замена их дизайну**.
4. `backends/blender_worker.py` — отдельный процесс с настоящим `bpy`;
   экспорт PNG и редактируемого `.blend` с keyframes. Измеряются вычисленная
   поза и деформированная сетка, а не только записанные значения контролов.
5. `run_probe.py` — coordinator без импорта `bpy`: snapshot входов,
   timeout/exit handling, H.264/AAC, полное обратное декодирование видео и
   аудио, QC-отчёт, SHA-256 manifest, идентичность входов/кода/runtime.
   `--resume` повторно проверяет каждый файл, а не доверяет наличию MP4.

Семь схем лежат в `studio/schemas/`: project, asset, rig, speech, shot,
manifest, quality report. Реальные входы пробы — `studio/production/smoke/`.

**Граница MVP:** project/asset/shot версии 1 намеренно принимают только
`technical_smoke` и `synthetic_rig_probe`. Передать семейную сцену и получить
вместо неё робота нельзя: несовместимый профиль отклоняется. Нет импорта
внешнего character package, asset registry, production layering, gait,
contacts, facial acting, phone alignment или lipsync. Поэтому общие
PIPE-01/PIPE-02 ещё не объявляются завершёнными.

## Фактический результат полного запуска

[Машиночитаемый отчёт](../studio/production/blender-smoke-report.json):
**14/14 технических проверок — pass**, coordinator/worker/encode/video decode/
audio decode завершились с кодом 0. Созданы и полностью декодированы
**24 кадра, 1920×1080, 24 fps, 1 секунда**, H.264/yuv420p + AAC mono 48 kHz.
MP4 — 179 499 bytes. Это короткая диагностика, не семейная серия.

| Измерение | Результат |
|---|---|
| Blender build | 4.5.0 · `8cb6b388974a` |
| FFmpeg | 7.0.2-static из imageio-ffmpeg |
| Рендер | Cycles CPU, 4 samples, denoise, AgX |
| Полный wall time | 875.2084 s — примерно 14 минут 35 секунд |
| Peak renderer RSS | 2 724 827 136 bytes — примерно 2.54 GiB |
| Реально доступные CPU | 2; в диагностическом config запрошено 8 threads, это не 8 ядер |
| Максимальная ошибка IK | 1.78814×10⁻⁷ m |
| Максимальная относительная ошибка длины кости | 3.14774×10⁻⁷ |
| Перемещение вычисленной вершины skinned mesh | 0.665380 m |
| Перемещение центра вычисленной jaw mesh | 0.190000 m |
| Аудио | 48 000 входных samples, 48 128 после AAC decode; 128 хвостовых samples |

[Hardware inventory](../studio/production/blender-hardware-inventory.json):
около 3.85 GiB физической RAM, swap нет, GPU device nodes не наблюдались.
Это **не realtime benchmark** и не доказательство возможности быстро
рендерить 40 секунд с тремя героями. Во время прогона наблюдался рост RSS;
причина не профилирована. До длинных сцен нужны memory-bounded worker/chunks,
CPU budget по реальному affinity и повторный stability test (PIPE-02/ENV-04).
Нельзя линейно распространить этот успешный короткий прогон на 960 кадров.

Дополнительные реальные проверки, не только mocks:

- [Отсутствующие native libraries → exit 1; без PNG и success manifest.
  Полный cache hit без нового worker, испорченная копия → exit 1, исходник
  сохранён; проверены фактические H.264/AAC streams](../studio/production/blender-negative-probes.json).
- [Повторно открыт экспортированный `.blend`](../studio/production/blender-scene-reload.json):
  на кадрах 0/12/23 меняются target и shape key **без** вызова нашего timeline.
- 70/70 unit tests MVP и 28/28 tracker tests пройдены отдельно: **98 всего**.
  [Команды и source hashes](../studio/production/verification.json).

ENV-02 закрыт только как этот runtime smoke. Общий G1, production package
contracts и полноценный render adapter остаются незавершёнными.

## Runtime и происхождение зависимостей

- Изолированный runtime в `.cache/blender-venv`, Python 3.11; официальный
  PyPI `bpy==4.5.0`. В текущем workspace `.venv-blender` — совместимый
  symlink на этот cache. Само окружение и binaries не сохраняются как Git-ассеты.
- [Version pins](../studio/production/blender-requirements.lock) включают
  NumPy 1.26.4. Legacy `studio/requirements.txt` требует NumPy 2.x:
  **нельзя смешивать эти окружения**. Это version-pinned список, пока не
  wheel-hash lock и не проверка всех уязвимостей.
- FFmpeg поставляется `imageio-ffmpeg==0.6.0`, не системным PATH-бинарником.
- Cycles CPU, AgX; Blender build и SHA-256 OCIO записывает worker.
- Версия 4.5.0 — проверяемый кандидат, не заявление «последняя версия» или
  одобрение этой patch-версии для длительного production.

Первый `import bpy` реально упал из-за отсутствующих `libXrender.so.1`,
`libXfixes.so.3`, `libXi.so.6`, `libxkbcommon.so.0`, `libSM.so.6`,
`libICE.so.6`, `libGL.so.1`. Установка Python wheel сама по себе не решила
проблему. Обычные apt mirrors недоступны в этой sandbox.

Для **изолированного эксперимента** использован опубликованный distro mirror
`eXtern-OS/eXternOS-Base`, commit
`ec0e026a2b09225b5a85369c3627aedaf6dc2a5f`: девять настоящих ELF-библиотек,
включая транзитивные GLX/GLdispatch. Ни ABI-заглушек, ни патча Blender нет.

- [Native lock с Git blob SHA-1 и SHA-256](../studio/production/sandbox-native-libs.lock.json).
- [Упакованные дистрибутивом copyright notices](../studio/production/sandbox-native-notices.json).
- [Проверяющий/загружающий инструмент](../studio/tools/prepare_blender_native.py)
  требует явного opt-in; проверяет точные размер и оба hash, не перезаписывает
  несовпадающие библиотеки. При fetch сохраняет notices рядом с ними.
- SHA обеспечивает целостность относительно mirror, **не подпись официального
  Debian/Ubuntu repository, не аудит безопасности и не одобрение provenance**.
  Старый системный архив нельзя незаметно превратить в production-зависимость.
  Бинарники остаются только в игнорируемом `.cache/`.

ENV-04 отдельно требует поддерживаемую OS/base image, проверенные patch
versions, системные пакеты из официального источника, licenses/security
review и повторный запуск на чистой среде **без mirror fallback**. До этого
полный G1 не закрыт. GPU-backend не проверялся; ускорение не обещается.

## Время, оси и сигналы

- Полуоткрытый диапазон `[0, 24)` → кадры 0…23; PNG sequence 000000…000023.
- 24 fps, 48 000 samples/s → ровно 2000 samples/frame; длительность 1 секунда.
- Rational fps использует `Fraction`, sample index вычисляется от абсолютного
  frame index с округлением к ближайшему (половины вверх), а не накоплением
  округлённой длительности кадра. Есть тест 30000/1001 fps.
- Метры, right-handed, Z-up, forward +Y. Legacy Y-up не конвертируется
  молча: он отклоняется. Полноценный migration adapter ещё предстоит.
- Аудио — негромкий синтетический диагностический тон. Нет дикторской реплики,
  forced alignment и попытки выдать движение shape key за артикуляцию по речи.
- AAC имеет размер блока 1024 samples: декодирование допускает только
  дополнительный хвост менее одного блока. Это не допуск для lipsync.

## Запуск

Предпочтительный путь: Linux с настоящими OS-пакетами `libxrender1`,
`libxfixes3`, `libxi6`, `libxkbcommon0`, `libsm6`, `libice6`, `libgl1`.
Их установку/подписи обеспечивает администратор или проверенный base image;
этот скрипт не требует root и не меняет системные каталоги.

```bash
python3 -m venv .cache/blender-venv
.cache/blender-venv/bin/python -m pip install -r studio/production/blender-requirements.lock

# Только контрактные unit tests — не запускают Blender:
.cache/blender-venv/bin/python -m unittest discover -s studio/tests -p test_pipeline.py -v

# На обычной проверенной Linux-среде:
.cache/blender-venv/bin/python -m studio.pipeline.run_probe
```

Только для повторения именно sandbox-эксперимента, с пониманием ограничения
provenance выше; загрузка идёт через `gh api`, без передачи токенов в чат:

```bash
python3 studio/tools/prepare_blender_native.py --fetch --accept-experimental-mirror
.cache/blender-venv/bin/python -m studio.pipeline.run_probe \
  --native-dir .cache/blender-native \
  --record studio/production/blender-smoke-report.json

# Завершённый идентичный job можно переиспользовать только после hash-проверки:
.cache/blender-venv/bin/python -m studio.pipeline.run_probe \
  --native-dir .cache/blender-native --resume
```

Если job уже есть, без `--resume` возвращается ошибка. Незавершённый job не
переиспользуется: частичный frame-level resume пока не реализован. Изменение
входов, кода или runtime даёт другой job ID. Исходные configs копируются до
старта worker. Ошибка/timeout не создают success manifest.

В текущем OS-provider fingerprint пока нет hash всех системных библиотек:
это ограничение cache identity, а не обещание полной воспроизводимости.
Новый запуск в другом окружении и production incremental builds — PIPE-03.

## Доказательства и ограничения приёмки

- [Журнал реальных попыток](../studio/production/blender-runtime-attempts.json):
  неудачный первый import, маленькая preflight-проба и отменённая дорогая
  настройка 12 samples / 2 threads. Отмена не выдается за успешные 24 кадра.
- Результат полного запуска сохраняется командой `--record` в
  `studio/production/blender-smoke-report.json`; это источник фактических
  чисел, exit codes, проверок, peak renderer RSS и вложенного manifest.
- Полные `.blend`, PNG, журналы, framehash, WAV и MP4 — производные в
  `studio/out/blender-smoke/<job-id>/`, не многомегабайтные Git-ассеты.
  Компактный отчёт хранится вне cache; отсутствие cache в новой копии не
  доказывает нового render pass и требует пересборки.
- Raw PNG hashes измеряются **до** добавления информационных надписей;
  тест изменчивости не проходит просто за счёт счётчика кадров в титрах.
- Проверяются endpoint IK (<0.005 m для диагностической сцены), сохранение
  длины костей, перемещение деформированной сетки и shape key. Это не
  походка и не проверка профессиональных норм опоры/контакта для семьи.
- Новые unit tests покрывают схемы, плохие ссылки/пути/каналы, временную
  сетку, перекрытия sample spans, испорченный cache, nonzero worker и timeout.
  Их fixtures прямо помечены как тестовые, не как медиа/voice alignment.
- `.github/workflows/pipeline-contracts.yml` запускает только unit tests с
  `jsonschema`; он не скачивает Blender/native mirror. Удалённый CI пока
  не запускался. Старый pilot suite в этом этапе не объявляется проверенным.

**Следующий шаг:** расширить PIPE-01 под настоящий внешний character/rig
package и затем PIPE-02 под его загрузку; параллельно закрыть ENV-04 и канон
ART-01. После deformation-ready папы — body/face rig, русский phone alignment
и только затем 8-секундная сцена «шаги → остановка → речь → жест». Числа
технической пробы не являются художественным одобрением этого персонажа.
