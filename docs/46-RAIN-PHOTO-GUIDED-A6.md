# 46 · Rain → мама A6: локальные фотоподсказки, мультяшный стиль сохраняется

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
