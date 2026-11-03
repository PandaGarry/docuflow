# 46 · Rain → мама A6/A7: локальные фотоподсказки, мультяшный стиль сохраняется

2026-11-03. Пользователь передал реальные фотографии и дополнительные изображения
в выбранной стилизации, оценив предыдущий проход как «уже неплохо». Это разрешение
уточнять внешний вид, **не** production/art/точное likeness approval.

## Конфиденциальность и приоритет источников

Личные изображения используются только для локальной визуальной сверки. Они
находятся в игнорируемой `studio/reference/`, не добавляются в Git/CI/artifact.
Скрипт A6 не открывает их и не публикует их имена, crops, hashes или embeddings.
Никакого распознавания личности/автоматического face fitting: ручные художественные
поправки. Review-board содержит только **уже опубликованный канонический арт**,
A5 и A6 native frames. Это не согласие на публикацию исходных личных фото.

Фото помогают оценить индивидуальные черты/естественность; существующий cartoon
canon по-прежнему задаёт стиль и общее оформление. Не превращаем героя в
фотореалистичную голову и не меняем master art/character.json без отдельного решения.
Не извлекаем точные пропорции/skin color из снимка с перспективой и тёплым светом.

## Что проверяем в A6

- Более расслабленная верхняя линия век, без произвольного уменьшения eyeballs.
- Чуть мягче midface, губы и nasal base вместо дальнейшего заострения крошечного носа.
- Менее светлый, более приглушённый коричневый цвет волос и мягче fiber bump/specular.
- Новая цельная crown/part surface вместо заметного стыка source crown и корней A5.
  Source crown лишь скрывается, остаётся редактируемой в native scene.
- Корни long locks погружены под crown, чёлка тоньше/асимметричнее, добавлены
  небольшие wisps вместо сплошной массивной завесы. Не финальный hair groom.
- Stock wardrobe и source rig сохранены. Добавленные волосы следуют оригинальным
  DEF-Head/lattice; collision/dynamics/полный animation approval не заявляются.

Форма лица переносится через все original corrective key coordinates; source
bone rest/weights/topology не переписываются. Total scene topology отличается:
новая crown и wisps — отдельные editable meshes. Blink/smile и девять native blink
samples проверяются отдельно от unit tests и художественной оценки.

## Первый code checkpoint

A6 скрипт и pure geometry/privacy tests написаны; native build ещё **не запускался**.
После native render нужно осмотреть roots/part/силуэт/eye closure и явно записать
оставшиеся дефекты. Выполнение numerical tests не заменяет качество картинки.
Рецепты A1–A5 и их отрицательные кадры сохраняются без перезаписи.

Восстановленный workspace снова оказался на старом HEAD; исходное состояние
сохранено stash, затем выполнен fast-forward к опубликованному 49d79c3. Два
мешавших старых ignored лога сохранены отдельно в cache. История не переписана.

## Пересборка

`python studio/tools/rain_mom_pass_a6.py` в pinned bpy 4.5.0 окружении с Ubuntu
libs из rain-study.yml. Настоящий official Rain ZIP/.blend с прежними hashes;
asset Python scripts disabled. Прямой sandbox download/native import не считается
доступным; actual native build выполняется GitHub-hosted worker на той же ветке.
PNG/JSON в `studio/reviews/rain-mom-a6`, packed .blend как 14-day Actions artifact.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**.
License: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/.
Modification notice: лицо/волосы как описано выше; endorsement не предполагается.

## A6 выполнен, обнаружен локальный art-дефект

Native run41641288358 success, frames commit37b55c5. 274 local tests passed;
source topology/rest signature unchanged, neutral restore=0m, new invalid=0,
9 blink samples finite. Цельная crown убрала бугристый стык A5, цвет более
приглушённый, видимые изменения eyelid/lip/midface небольшие, стиль сохранён.
Личные фотографии не читались native worker и не публиковались.

При просмотре three-quarter/front виден тёмный зазор у виска и резкий переход
crown к боковым locks. A6 не объявляется законченной причёской. Добавлен A7:
тот же private-local workflow и лицо/материал A6; cap продлён к вискам без
опускания central forehead hairline, верхние curtain roots сильнее погружены
под crown и истончены для меньшей ступеньки. A6 evidence/recipe сохранены.
A7 на момент этого checkpoint ещё не отрендерен.

## Текущий итог A7: получен и просмотрен

Native run [41642309803](https://github.com/PandaGarry/docuflow/actions/runs/41642309803)
успешен, actual frames commit **1272568**. **275 local tests passed**; native job
отдельно выполнил 238 contract tests, shader probe, загрузку официальной Rain,
реальную адаптацию, шесть renders и девять blink sample evaluations.

- [Канонический стиль / A5 / A7](../studio/reviews/rain-mom-a7/comparison-reference.png)
- [Три четверти](../studio/reviews/rain-mom-a7/candidate-three-quarter.png)
- [Профиль](../studio/reviews/rain-mom-a7/candidate-profile.png)
- [Blink](../studio/reviews/rain-mom-a7/candidate-blink.png) /
  [smile](../studio/reviews/rain-mom-a7/candidate-smile.png)
- [Receipt](../studio/reviews/rain-mom-a7/report.json) /
  [отдельная visual review](../studio/reviews/rain-mom-a7/visual-review.json)
- [Редактируемый packed .blend, ~67MB](https://github.com/PandaGarry/docuflow/actions/runs/41642309803/artifacts/13233013751)
  — expires **2026-11-17 13:15:55 UTC**. PNG/JSON/recipes в Git остаются.

Все шесть PNG hashes перепроверены после получения. Original mesh topology/rest
rig signature сохранены; новые hair meshes отдельны, source crown скрыта,
не удалена. Neutral restore=0m, новых invalid drivers нет, один source spine
invalid сохраняется. 9 finite blink samples не равны полноценной facial QC.

**Визуально:** A5 макушечные бугры ушли, цвет/чёлка мягче, большой чёрный зазор A6
уменьшен. Но стыки cap/clumps остаются видимыми как швы/ступеньки в профиль,
пряди пластинчатые и слишком регулярные, crown ещё helmet-like. Лицо сохраняет
черты Rain и лишь частично приближено к референсам. Это **не** финальный groom,
точная photo likeness, фотореалистичная копия или подтверждённый киноуровень.

Privacy проверена: все пользовательские вложения локально ignored; tracked
`studio/reference` содержит только README. Build не читает эти вложения; в Git,
CI inputs, review-board и packed native scene нет их копий/crops/фотохешей.
Публичная каноническая картинка уже была в репозитории, masters не менялись.
Статус ART/RIG/production acceptance не переключён, одежда не переоформлялась.

Пересборка текущего результата: `python studio/tools/rain_mom_pass_a7.py` в
pinned native окружении и с official download access. Дальше: интеграция стыков,
более естественные волны/слои и продолжение authored face refinement с проверкой
в разных ракурсах и в движении. Не переносим успех CI на художественную оценку.
