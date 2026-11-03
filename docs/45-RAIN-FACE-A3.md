# 45 · Rain → мама: направленная переработка лица A3

2026-11-03. После просмотра A2 пользователь прямо потребовал более явного
сходства. Одобрение продолжения не означает приёмку лица/рига/production.
A1/A2 и канонический turnaround сохраняются без перезаписи.

## Что меняем относительно A2

Изучен увеличенный crop лица **из настоящего канонического turnaround**, не
новая картинка. В отличие от A2 (mostly tone/softness), A3 меняет признаки:

- Уже/короче нос, немного приподнятый кончик; не только оттенок кожи.
- Более узкая нижняя челюсть и короче нижняя часть лица вместо широкой челюсти Rain.
- Шире линия рта, меньше толщина/выступание губ, подняты уголки в rest geometry.
- Небольшая коррекция внешнего контура глаз; расстояние между их центрами сохранено:
  на референсе глаза тоже крупные, поэтому произвольное сильное уменьшение неуместно.
- Менее выступающие уши, мягкая дуга бровей, серо-голубой вместо ярко-цианового iris.
- Тёплый тон волос, привязанные к топологии blush/lip colors, без ретуши PNG.

Это не 3D-скан/точный landmark fit. Поле деформации задано в native rest meters,
одинаково переносит **все** оригинальные corrective shape keys и eye/lash/gum
meshes. Skeleton rest, weights, исходные drivers и topology не переписываются.
До native проверки совместимость поз не считается доказанной.
Стоковая **форма** причёски и одежда пока сохранены; hair silhouette остаётся
существенным отличием от эталона и потребует отдельной авторской работы.

## Мимика и оценка

Вместо закрытия только верхнего века тестируется upper/lower actuator mix 70/30,
с одинаковой схемой на source и candidate. Это **проверяемая гипотеза**, не
заранее объявленное исправление. Сохраняются blink/smile PNG, nine-sample native
blink sweep и возврат в neutral. Finite coordinates не доказывают хорошую анатомию.

Board включает **эталон / A2 / A3**. A2/A3 имеют ту же camera/light/pose; эталон —
2D art с другим освещением. Individual native frames остаются нетронутыми.

На момент первого code checkpoint новый build ещё **не выполнен**: нельзя
заявлять визуальное улучшение/успешное моргание до просмотра его кадров.

## Воспроизведение

`python studio/tools/rain_mom_pass_a3.py` в окружении pinned native lock и Ubuntu
libraries из rain-study workflow. Source acquisition тот же exact official Rain
ZIP/.blend с hash checks и отключённым исполнением встроенного Python. Sandbox
прямой download не работает; native worker — GitHub Actions на прежней ветке PR3.
PNG/JSON публикуются в `studio/reviews/rain-mom-a3`, editable packed .blend —
14-day Actions artifact. Heavy binary в Git не добавляется.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**.
License: CC BY 4.0 https://creativecommons.org/licenses/by/4.0/.
Change notice: лицо/палитра изменены как описано выше; endorsement не предполагается.
