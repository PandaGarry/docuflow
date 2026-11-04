# 45 · Rain → мама: лицо и обрамление A3–A5

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

A5 diagnostic resolved the real exception: a **fresh** bpy 4.5 Principled node
has no exposed `Weight` socket, unlike the legacy socket retained in the loaded
source inspection. The attempt to set it raised KeyError. Removed that internal
socket assumption; fresh shader uses ordinary default BSDF weighting. An explicit
native shader-construction probe now runs before acquiring the large source.
The earlier wording “Weight=1” described intent, not a completed native result.
Bounded traceback is preserved as failure-legacy-weight-socket.txt. The separate
log-capture directory error is preserved as failure-log-redirection.txt.

## Текущий итог: A5 действительно отрендерен и просмотрен

Run [41608973796](https://github.com/PandaGarry/docuflow/actions/runs/41608973796)
**success**, frames commit **f93a164**. Предыдущие A5 failures сохранены как
диагностика, а не скрыты. **267 local tests passed**; native job отдельно
выполнил 230 contract tests, native shader probe и фактический Blender build.

- [Эталон / A2 / A5](../studio/reviews/rain-mom-a5/comparison-reference.png)
- [Три четверти](../studio/reviews/rain-mom-a5/candidate-three-quarter.png)
- [Профиль](../studio/reviews/rain-mom-a5/candidate-profile.png)
- [Полный рост](../studio/reviews/rain-mom-a5/candidate-full.png)
- [Blink](../studio/reviews/rain-mom-a5/candidate-blink.png) /
  [smile](../studio/reviews/rain-mom-a5/candidate-smile.png)
- [Technical receipt](../studio/reviews/rain-mom-a5/report.json) /
  [Visual review](../studio/reviews/rain-mom-a5/visual-review.json)
- [Editable packed .blend artifact, ~67MB](https://github.com/PandaGarry/docuflow/actions/runs/41608973796/artifacts/13217354395)
  — expires **2026-11-17 09:14:20 UTC**. PNG/JSON и recipes остаются в Git.

Сохранены topology всех **исходных** meshes и original rest rig signature.
Добавлено 11 новых hair clumps; total scene topology поэтому не идентична
исходнику. После возврата из pose head error=0m, новых invalid drivers нет,
9 A5 blink samples finite. Старый original spine invalid driver не исправлен.
Head/weights/rig не заменены процедурной фигурой. Asset Python scripts disabled.
Все шесть individual native PNG hashes перепроверены после получения из CI.

**Визуально:** появился более близкий тип лица/обрамления вместо короткой Rain;
чёрный shader failure устранён. **Но НЕ профессионально завершённый groom:**
пряди слишком крупные/пластинчатые, root/crown joins видны, волны недостаточно
естественные, цвет выглядит слишком светлым. Плоскости лица/skin/eye region
ещё не равны эталону. Это первый editable long-hair look study, не красивый
финал, не анатомическая/актёрская/пользовательская приёмка. Wardrobe unchanged.

Следующий этап: интеграция roots/пробора/crown, более естественная асимметрия
локонов и palette correction; затем дальнейшая авторская доводка facial planes
и проверка head motion/shoulder clearance. Одежду пока не переоформляем.

Пересборка текущей ревизии: `python studio/tools/rain_mom_pass_a5.py` в pinned
native окружении с официальным download access; workflow содержит Ubuntu libs.
