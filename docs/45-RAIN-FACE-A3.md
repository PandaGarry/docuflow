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

## A3 native результат

Run 41606481996 успешно выполнил реальную адаптацию и render, commit da3bc8a.
Есть actual reference/A2/A3 board, front/three-quarter/profile/full, smile/blink
и paired source expressions. 264 local tests passed. Original topology/rest
signature сохранены, neutral restore=0m, новых invalid drivers нет. 9 native
blink samples/source и 9/candidate finite, **не** полный animation acceptance.

Просмотр: новая форма рта/челюсти, меньший нос, более серые глаза и светлые волосы
дают реальное отличие от A2; long/wavy silhouette и parted bangs эталона всё ещё
отсутствуют, поэтому likeness недостаточно явная. Balanced upper/lower blink
сводит lash contour лучше предыдущего setup, но поверхности век ещё не финальные.

## A4: добавить обрамление лица, одежду не менять

Чтобы не выдавать очередную перекраску за сходство, добавлен следующий native
build: длинная волнистая hair curtain и два swept center-parted face-framing
clumps. Это **новые редактируемые hair meshes на настоящей Rain**, не замена
персонажа и не AI-дорисовка. Исходная crown остаётся; ponytail/strand/band лишь
скрываются, не удаляются. Новые волосы привязаны к исходным DEF-Head/lattice.
Веса/body/rest bones и topology всех исходных mesh сохраняются; total scene
топология закономерно увеличивается из-за новых hair meshes. Носовая база ещё
немного сужается с переносом всех facial corrective keys.

A4 требует просмотра: совпадение стиля новых прядей/исходной crown, швы,
пересечения с плечами/ушами/лицом, силуэт в профиль. Это groom study без hair
simulation/collision acceptance. На момент code checkpoint A4 **не отрендерен**;
успех/похожесть нового groom заранее не заявляется.

## A4 visual failure и исправление A5

Run 41607338326/commit 583a08a выполнил настоящий native render, но **A4
отклонён**: новые пряди в copied Rain material выглядят полностью чёрными,
между back/side locks видны зазоры, пробор и crown ещё не состыкованы.
Technical job success и finite head не отменяют очевидный визуальный fail.
Изображения A4 сохраняются, не выдаются за готовую причёску.

A5 сохраняет лицо A3/A4 и настоящую Rain. Для добавленного groom используется
отдельный Principled shader (Weight=1) без зависимостей от source-object shader
attributes, тёплый brown fiber variation. Материал применяется также к stock
crown для единства. Curtain locks расширены/перекрываются, side radius увеличен,
волны face-framing locks усилены, исходный widow peak приподнят в пробор с
переносом всех hair shape keys. Добавлен 9-point blink sweep в текущем A5,
но collision/dynamics/art acceptance по-прежнему не объявляются.
Новый A5 render на момент code checkpoint ещё не получен.

A5 first native run 41608190718 exited 1 before publication (no A5 output yet).
GitHub's redirected raw log host is unavailable from this sandbox. Workflow now
preserves a bounded worker stderr/stdout tail on failure in the same branch,
while retaining the original failed job exit state. This is diagnostics, not a
claim that the shader repair rendered successfully. Local bpy import is also
blocked by missing libXrender; native execution remains in the Ubuntu CI worker.
