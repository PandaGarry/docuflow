# 43 · Локализация регрессии кисти и ход исправления

**2026-11-03 · рабочая итерация; не художественная приёмка.**

## Публикация

Накопленный код, пять PNG и отрицательный R4 review опубликованы в текущую
ветку `arena/4c8ed03c-docuflow`, PR #3. Коммит `5c120fc`, merge с ранее
опубликованными коммитами пилота `b66f665`; force-push не использовался.
На `b66f665` оба GitHub Actions checks прошли: contract/process tests и
planning tests. Это **не** запуск Blender и не artistic acceptance.
При проверке чистого checkout исправлена ошибочная зависимость одного pure
contract test от генерируемого .blend: runtime file verification не отключалась,
source provenance по-прежнему проверяется отдельным unit test.

## Что локализовано

`check_lookdev.py` теперь сохраняет худший triangle, исходные/деформированные
world coordinates, площадь и реальные vertex-group weights для каждой кисти.
Добавлен `--inputs` для отдельных revision fixtures; старый R3 checker неизменён.

Новый запуск на восстановленном R4 воспроизводит **15/17 FAILED**. Дефект
локализован **у перехода ладони в основание большого пальца**, симметрично:
R triangle 33385 / vertices 1045, 9071, 13955; L triangle 33248.
Rest triangle area ≈1.9883e−7 m², posed ≈1.4811e−6 m², ratio ≈7.449.
Два близких по расположению vertices имеют существенно разные thumb weights,
а два иных — одинаковые. После изменения формы thenar/palm исходное cage
interpolation не обязательно даёт гладкое поле влияний в пространстве.
Это проверяемая гипотеза механизма растяжения, не доказательство всей анатомии.

Полные данные: `studio/production/dad-r4-localized-extremes.json`.
Результаты документа 42 и прежние receipts не переписаны.

## Первый эксперимент R5 — отклонён

Отдельный `refined_hands.py` и `build_dad_handfix.py` сохраняют геометрию,
топологию, tip IDs, R4 материалы и body rig. Изменяются только thumb/hand weights.
Простое пространственное поле axial onset + radial falloff уменьшило max area
ratio до ~2.165, **но** внесло сжатие до ~0.00822 и edge stretch ~3.03859.
То есть результат всё ещё **FAILED**, новый дефект не скрывается улучшением
одного показателя. Trial report и package сохранены в `production/experiments`.
Лимиты и позы не изменены. Этот эксперимент не является принятым исправлением.

Далее проверяется геометрически взвешенное сглаживание исходного поля на
mesh adjacency вместо замены всего thenar field. Обязательны повторные 17
poses, все 72 промежуточных кадра и осмотр нового native hand close-up.
Киноуровень, anatomy/likeness/face-rig и production swap остаются непринятыми.
