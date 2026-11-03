# 39 · Внешний 3D-пакет и ограниченные render workers

> Историческая запись r1-среза. Следующий body-rig r2 и новые проверки —
> [документ 40](40-BODY-RIG-AND-CONTACT-PROBES.md). Receipt 149 tests этой
> итерации сохранён в `external-package-verification-2026-11-03.json`;
> актуальный общий receipt — `verification.json`. Producer hashes старых
> рендеров не заменены хешами нового кода.


**Дата:** 2026-11-03. **Область:** исполнимый preview модели/рига и управление
ресурсами. Не финальный дизайн папы, не ходьба и не артикуляция по записи.

## Что изменилось относительно технического робота

Вместо создания диагностической геометрии внутри renderer новый путь
**загружает самостоятельный `.blend` package**. Отсутствующую модель или
контрол он не заменяет роботом/PNG. Для проверки создан оригинальный
процедурный блокинг папы: коричневые волосы/борода, серый свитер, тёмные
джинсы, объёмные глаза, кисти с пятью отдельными пальцами. Это простые
объёмные заготовки, не production topology и не подтверждённое сходство.

- Авторинг: `studio/tools/build_dad_blockout.py`. Он используется отдельно
  от renderer, а не подставляется как fallback при ошибке импорта.
- Полученный пакет: `studio/out/dad-blockout/{dad.blend,package.json}`.
- [Зафиксированные метаданные r1](../studio/production/dad-preview/package-r1.json)
  содержат SHA-256 `.blend` и source recipe, revision и семантические bindings.
  Бинарный `.blend` остаётся производным в игнорируемом `out/`.
- Поддержаны IK targets кистей, Euler rotations объектов/костей, shape keys
  открытия рта и закрытия глаз. Шевеление рта здесь **не lipsync**.
- Ноги и обувь статичны; body/foot rig, походка, пальцевые суставы, корректирующие
  формы, полноценные веки/глаза и лицевая артикуляция ещё предстоят.

## Контракты v2 и импорт

Новый `studio/pipeline/packages.py` и четыре локальные JSON Schema:

- `asset-package.v2.schema.json`: `.blend` path/hash, collection, revision,
  оси, метры, radians, provenance recipe/hash, semantic bindings и IK probes;
- `project.v2.schema.json`: профиль `rig_preview`, rational fps, разрешение,
  samples/threads/seed и отдельный resource budget;
- `shot.v2.schema.json`: ссылки на проект, точную revision ассета, полуоткрытый
  диапазон и покадровые управляющие кривые;
- `render-manifest.v2.schema.json`: identity входов/кода/runtime и hashes файлов.

V1 smoke API остаётся отдельным и не интерпретирует v2 молча. Неподдерживаемые
оси/единицы, незнакомые поля/версии, URL, выход пути из workspace, неверный hash,
неверная revision, отсутствующий канал или неверная форма данных — ошибки.

Importer добавляет только заявленную collection через Blender libraries API,
не открывает исходную сцену вместо рабочей и не наследует её camera/world/render
settings. Scripts auto-execute выключен; drivers, неподдерживаемые типы объектов/
модификаторов и внешние непакованные изображения отклоняются. Поддерживаемый
пакет — meshes, armature и empties с явными numeric controls.

**Граница доверия:** только доверенные локальные авторские `.blend`.
Hash подтверждает байты, не авторство, лицензию или отсутствие Blender CVE.
Это не безопасная песочница для чужих файлов. `project-original` — декларация
для нашей процедурной геометрии, не автоматическая юридическая проверка.
`art_status` пока только `unreviewed`; generic production/approval workflow
не считается завершённым (PIPE-01/02 и QA-01 остаются открыты).

Перед запуском входы и `.blend` копируются в job snapshot и повторно проверяются.
Изменение входов, кода, model hash или runtime меняет job ID. Экспортируемая
preview-сцена сохраняет полноценные Blender keyframes на всю длину шота.
Геометрия одного пакета используется во всех кадрах, без новых картинок лица.

## Ограничение ресурсов и возобновление

`studio/pipeline/resources.py`:

- число render threads ограничивается реальным CPU affinity;
- отдельный новый процесс на каждый небольшой батч;
- watchdog измеряет сумму RSS процесса и descendants, проверяет timeout;
- на ошибке/лимите завершается Unix process group, а не только parent;
- nonzero exit, timeout и превышение RSS не превращаются в success;
- self-reported peak RSS worker дополнительно проверяется после завершения.

Это **sampled watchdog**, не жёсткий cgroup/RLIMIT и не security sandbox.
Короткий всплеск может превысить бюджет до следующего sample, shared pages
в RSS descendants могут считаться повторно. Защита уменьшает риск, но не
доказывает невозможность OOM на любом asset. Причина роста native RSS из
предыдущего прогона не установлена; здесь используется ограничение времени
жизни процесса, а не заявление «утечка устранена».

`studio/pipeline/render_package.py`:

1. получает эксклюзивный job lock;
2. делит `[start,end)` на небольшие интервалы;
3. для каждого запускает worker, проверяет реальные PNG, размер, coverage,
   IK residual, resource report и artifact hashes;
4. только после этого атомарно пишет complete checkpoint;
5. при `--resume` переиспользует **только** совпадающие и проверенные chunks;
6. незавершённую попытку не принимает за готовые кадры: новый retry имеет
   отдельную attempt-directory, журналы ошибки остаются;
7. после всех батчей собирает silent H.264 MP4 и полностью декодирует его,
   проверяя frame count, PTS, rational timebase и native dimensions;
8. complete manifest появляется только после всех этих проверок.

При финальном cache hit проверяются также обязательные файлы и все hashes:
нельзя удалить видео и убрать его из manifest, оставив фиктивный success.
Manifest — проверка целостности, не криптографическая подпись доверенного автора.

Разрешение пробы — **960×540, 24 fps, 48 кадров / 2 секунды**, не upscale до
1080p. Бюджет: 4 кадра/worker, 1536 MiB RSS, 180 секунд/worker. Профиль имеет
4 samples + denoise, AgX Medium High Contrast, exposure −0.5, ограниченный
bounce budget. Эту скорость/память нельзя напрямую сравнивать с прежним
1080p smoke: изменены разрешение, профиль и геометрия.

Аудио намеренно отсутствует. Выходные RGB интерпретируются как sRGB display
AgX; преобразование YUV использует BT.709 matrix и tags с sRGB transfer.
Это preview, не готовый broadcast/mastering pipeline.

## Реальные проверки, а не только mock tests

[Журнал integration probes](../studio/production/dad-package-integration.json):

- намеренная пауза после первого полного chunk возвращает **75**, а не
  успешное завершение всего ролика; финального manifest в этот момент нет;
- продолжение использует первый chunk без повторного рендера;
- настоящие Blender jobs с отсутствующими collection/control завершаются
  с кодом 1, без PNG, complete chunk и complete manifest;
- низкий лимит RSS действительно останавливает настоящий bpy worker;
- unit tests отдельно запускают реальные Python subprocess: nonzero,
  timeout, выделение памяти сверх лимита, остановку descendants.

Unit fixtures для file integrity прямо помечены как **не медиа**. Contract
validation не объявляется Blender render pass. Новый suite —
`studio/tests/test_package_pipeline.py` (51 tests); прежние 70 MVP и 28 tracker
проверяются отдельно. CI устанавливает только jsonschema/psutil и не рендерит
Blender. Удалённый запуск CI в этой итерации не подтверждён.

## Запуск

Из корня репозитория с подготовленным изолированным runtime из документа 38:

```bash
# В нормальной production-среде используются настоящие поддерживаемые OS libs.
# Только для уже описанного sandbox-эксперимента:
LD_LIBRARY_PATH="$PWD/.cache/blender-native" \
  .cache/blender-venv/bin/python studio/tools/build_dad_blockout.py

.cache/blender-venv/bin/python -m studio.pipeline.render_package \
  --native-dir .cache/blender-native \
  --record studio/production/dad-preview-report.json

# Проверка cache или продолжение после незавершённого job:
.cache/blender-venv/bin/python -m studio.pipeline.render_package \
  --native-dir .cache/blender-native --resume

# Без bpy: unit/process-guard tests, 121 tests в этих двух suites:
.cache/blender-venv/bin/python -m unittest discover -s studio/tests \
  -p 'test_*pipeline*.py' -v
python3 -m unittest discover -s studio/tests -p test_production_status.py -v
```

`--max-new-chunks 1` предназначен для проверяемой паузы; возвращает 75,
сохраняет checkpoint и не создаёт итоговое видео. После этого продолжить
тем же набором входов и `--resume` без ограничения. Самовольная смена
бюджета/кода/пакета — другой job, не продолжение под старым ID.

Recipe воспроизводит геометрию, но bit-identical `.blend` при пересохранении
не обещается. После пересборки обновляется package hash и получается новый job.
Зафиксированный package-r1.json — evidence конкретной сборки; свежий renderer
по умолчанию читает свежий `studio/out/dad-blockout/package.json`.

## Результат полного прогона

[Фактический отчёт](../studio/production/dad-preview-report.json):
**48 настоящих кадров, 960×540, 24 fps, 2 секунды**, MP4 полностью декодирован.
Видео H.264, без аудио, 105 358 bytes.
[Полный компактный manifest](../studio/production/dad-preview-manifest.json)
сохранён вне cache, без бинарных моделей/PNG. Артефакт — `dad-preview.mp4` в
cache-directory из отчёта; никакого upscale до 1080p.

| Измерение | Результат |
|---|---|
| Батчи / отдельные PID Blender | 12 × 4 кадра / 12 разных PID |
| Продолжение | 1 проверенный батч reused, 11 новых |
| Ранее сохранённый checkpoint | mtime не изменён: первые 4 кадра не перерендерены |
| CPU threads | 2 фактически, по affinity |
| Peak worker RSS / observed group RSS | 833 417 216 bytes, около 795 MiB (0.776 GiB) |
| Заданный RSS budget | 1536 MiB на worker group |
| Maximum IK endpoint residual | 7.37203×10⁻⁵ m |
| Реальное перемещение вершины skinned sleeve | 0.850685 m |
| Сумма wall time всех 12 worker | 443.5461 s |
| Wall time продолжения | 408.3461 s; не включает первый батч до паузы |
| Encode / decode exit codes | 0 / 0 |

Экспортированная сцена заново открыта в Blender. На кадрах 0/3/4/12/22/37/47
контролы совпали с JSON-кривыми без вызова нашего `apply`; max error
1.43052×10⁻⁷. Таким образом, keyframes сохраняются и через границы батчей.
Это проверка данных/воспроизведения, не художественная приёмка движения.

После полного прогона исправлен отдельный edge case: **пустой diagnostic log —
законный файл с размером 0**, его hash тоже должен попадать в manifest при
retry. [Текущая версия дополнительно проверена живым четырёхкадровым прогоном
из двух worker](../studio/production/package-empty-log-regression.json), с
паузой/продолжением и таким файлом. Это не выдаётся за второй 48-кадровый рендер.
[Отчёт короткого regression](../studio/production/package-short-regression-report.json).

Полный старший manifest повторно проверен текущим validator. Успешный полный
cache hit, изменение байта в PNG → exit 1, точное восстановление → exit 0
проверены на коротком regression-cache; основной 48-кадровый cache не менялся.
Старый job ID не переназначен новому коду: `code_identity` намеренно инвалидирует
автоматический reuse после изменения схемы/кода.

**Итого:** 51 новых тестов пакетов/ресурсов + 70 прежних MVP + 28 tracker =
**149 unit/process tests**. [Команды и source hashes](../studio/production/verification.json).
Это не 149 проверок художественного качества и не доказательство исправления
native memory leak или готовности полной 960-кадровой сцены.

## Что пока не принято

Официальная поддерживаемая base image/native provenance, integrity/security
review версий, long-run 960-frame stability и hard memory isolation не закрыты.
Нет утверждения пользователя по сходству/дизайну модели, deformation topology,
полноценному body/face rig и актёрской игре. Двухсекундный жест не заменяет
8-секундный контрольный шот со стартом шага, остановкой и речью.

Следом — likeness/моделинг и чистая topology папы, расширенный body/face rig,
общие production contracts/approval gates. Наличие работающего preview path
не переводит эти задачи автоматически в done.
