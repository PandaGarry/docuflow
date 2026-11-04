# 44 · Rain v3 → мама: первый ограниченный эксперимент

2026-11-03. Рабочая среда восстановилась. Локальная копия синхронизирована
fast-forward с опубликованным 295d1ae; восстановленный workspace stash
сохранён, не удалён. Работа идёт на прежней ветке PR #3.

Цель: использовать настоящий готовый Rain v3, а не процедурную замену.
Первый проход — кожа, телосложение и мягкие facial proportions; одежда
остаётся исходной. Эталон: `studio/characters/mom/master/turnaround.png`,
палитра/описание: `studio/characters/mom/character.json`.

## Получение исходника и проверка

Прямой официальный download из sandbox заканчивается SSL EOF. GitHub Actions
используется как реальная native render-среда: скачать официальный архив,
проверить SHA256, открыть настоящий .blend и опубликовать PNG/inspection в
**эту же** ветку. Это не перенос чужого web-export и не AI-иллюстрация.

Source page: https://studio.blender.org/characters/rain/v3/
Archive: https://studio.blender.org/download-source/files/ee/a7/eea73e55dba1cea31c09848df6a794b2-4.zip
License: CC BY 4.0, https://creativecommons.org/licenses/by/4.0/
Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**.

Ожидаемые archive/blend hashes сверены с независимым публичным receipt
TheDudeCommits/CodexOfWar, ArtSource/P10/Round003/README.md. Это вторичный
hash witness, **не** официальная цифровая подпись. Сам download берётся
только с Blender Studio; mismatch — остановка, не молчаливая замена.
Исходный файл внутри архива может называться rain_v3.2.blend, хотя карточка
пакета называется Rain v3. Скрипт выбирает его по точному SHA, не по имени.

Автовыполнение встроенного Python отключено. Сначала исследуются meshes,
materials, shape keys, controls и invalid drivers. Наличие нейтрального кадра
не означает проверку мимики/рига; при проблемах сначала аудит и диагностика.
Нативный runtime — pinned bpy 4.5.0 и Ubuntu packages, без sandbox ELF mirror.

## Статус первого checkpoint

Добавлены acquisition/native inspection tool и отдельный workflow. Его первый
запуск пока **не подтверждён**. До получения/осмотра actual PNG нет заявления,
что Rain загружена, адаптирована, похожа на эталон или пригодна для анимации.

Дальше: осмотреть исходные кадры и inspection, затем внести только умеренные
изменения. Сравнивать исходник и кандидат при одинаковых camera/light/settings;
отдельно проверить выражения. Source rig, исходные файлы и прежние receipts
не переписываются. Новые кадры публикуются в studio/reviews/rain-study.

## Исходник действительно получен

Native workflow 41600774038 успешно завершён. Commit 5f67176 содержит
реальные `source-full.png`, `source-face.png` и native inspection. Официальный
архив и .blend совпали с pinned hashes, bpy 4.5.0 открыл модель, никакой чужой
модифицированный GLB не использован. В исходном pre-evaluation inspection
отмечен один invalid object driver (DEF-Spine3 bbone_easeout); это не скрывается.

Добавлен фактический A1 build: мягкое расширение талии (до 14%), глубины (до 9%),
нижних щёк/подбородка; сокращение выступания носа не более 4mm; уменьшение
толщины бровей, их тёплый цвет. Карта применяется одинаково ко всем координатам
всех исходных shape keys и к одежде для сохранения посадки, без смены её дизайна.
Rest bones, weights, topology и исходные драйверы не переписываются. Это не
доказательство, что все возможные позы совместимы: нужны отдельные native checks.
Кожа: сохранён texture pipeline, добавлены lift/peach tint с целевым #E8B48F;
этот hex не объявляется точным экранным цветом при освещении/AgX.

Новый workflow должен отрендерить A1 full/face/three-quarter и blink/smile.
Проверка мимики использует реальные ACT controls → исходные drivers → исходные
shape keys, не выключает drivers и не подменяет их прямым key.value. В отчёте
сохраняются фактические responses и статус partial/blocked. Все ещё НЕ выполнено:
полный animation sweep, phonemes, likeness approval, professional art acceptance.
Нативный редактируемый .blend с packed textures сохраняется как Actions artifact
на 14 дней, не засоряет Git. Небольшие PNG и receipt остаются в Git постоянно.

## A1 опубликован, ошибки тестовых поз сохранены

Run 41601612951, commit ce24c5a: actual A1 PNGs и .blend artifact, topology и
rest rig signature сохранены; новых invalid drivers нет. После возврата в
neutral maximum evaluated head error = 0m. Но A1 smile **НЕ удалась**: coarse
control samples дали только 0/1, и выбор ближайшего к .5 попал в 0. Изображение
candidate-smile поэтому идентично neutral; report честно содержит partial.
A1 blink использовал слишком большой control input (-.1 вместо около -.04),
так что достижение clamped shape value 1 само по себе нельзя считать хорошим
закрытием век. Эти кадры не принимаются за корректную мимику.

A2 оставляет геометрию A1, делает брови темнее (#6B4F38) и исправляет именно
control positioning: bounded bisection внутри существующих drivers, целевые
blink .99999 и smile .5. Публикуются **и source, и candidate** expression frames
с одинаковым native control solver: можно отличить проблемы исходника от
внесённых изменений. A1 files/recipe не переписываются. A2 execution на момент
этого code checkpoint ещё не подтверждён.

Локальные проверки: 253 tests (включая старый pilot с отдельно установленным
opencv-python-headless 4.10.0.84), до добавления трёх A2 solver tests. Pinned
native lock не менялся. Исторические dad/R5 receipts и canonical art сохранены.

## A2 выполнен и просмотрен

Run [41602307063](https://github.com/PandaGarry/docuflow/actions/runs/41602307063)
успешен, реальные кадры опубликованы в commit **0976a86**. Локально **256 tests
passed**; native job отдельно выполнил 207 pipeline + 12 Rain contracts и
planning validate, затем открыл официальный .blend, изменил и отрендерил его.
Эти числа не являются художественным pass.

- [До/после](../studio/reviews/rain-mom-a2/comparison.png)
- [Три четверти](../studio/reviews/rain-mom-a2/candidate-three-quarter.png)
- [Улыбка](../studio/reviews/rain-mom-a2/candidate-smile.png)
- [Закрытие век](../studio/reviews/rain-mom-a2/candidate-blink.png)
  и [тот же actuator setup на исходнике](../studio/reviews/rain-mom-a2/source-blink.png)
- [Native report](../studio/reviews/rain-mom-a2/report.json)
  и [visual review](../studio/reviews/rain-mom-a2/visual-review.json)
- [Редактируемый .blend с packed textures, 66MB artifact](https://github.com/PandaGarry/docuflow/actions/runs/41602307063/artifacts/13215237140)
  — expires **2026-11-17 08:21:30 UTC**. PNG/receipts в Git постоянны.

Blink inputs теперь примерно -.039996m ACT local Y вместо -.1;
Smile использует примерно .00625m ACT local Z и действительно достигает .5,
максимальное движение candidate head ~6.40mm. Topology/rest bone signature
сохранены, после pose restore head error=0m, новых invalid drivers нет.
Старый spine driver остаётся invalid и в source, и в candidate.

**Художественная оценка НЕ пройдена.** При закрытии век виден неубедительный
контур ресниц/поверхности века — и на исходнике с тем же setup, и на A2.
Нужно исследовать совместное управление upper/lower lids и привязку lashes,
а не выдавать shape value=1 за хороший blink. Улыбка слишком сдержанная для
актёрской приёмки. Лицо всё ещё узнаётся как Rain, не как точная каноническая
мама; глаза/губы/плоскости лица, волосы и look-development требуют работы.
Одежда пока не переоформлялась. Пользователь ничего из этих кадров ещё не одобрял.

### Пересборка

Python 3.11 + `studio/production/blender-requirements.lock`, системные библиотеки
Ubuntu перечислены в `.github/workflows/rain-study.yml`. В среде с доступом к
официальному Blender Studio download:

```bash
python studio/tools/rain_study.py           # genuine source inspection/baseline
python studio/tools/rain_mom_pass_a2.py     # editable native candidate + paired stills
```

В sandbox прямой download всё ещё не подтверждён: текущие native результаты
получены именно в GitHub-hosted worker. Исходные asset Python scripts не
исполнялись; bundled UI не объявляется отдельно проверенным. Отчёт содержит
hashes исходника, канона, всех трёх build/render scripts и семи individual PNG.
