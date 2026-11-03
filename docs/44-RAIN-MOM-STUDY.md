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
