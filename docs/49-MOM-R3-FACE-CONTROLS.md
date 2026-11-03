# 49 · Мама R3: сохранить найденное направление, губы и согласованная улыбка

2026-11-03. Пользователь положительно оценил R2: «Ты очень близок … выглядит
очень и очень хорошо» и попросил продолжать. Это поддержка направления, не
приёмка ещё не исправленного blink/полного acting. R2 сохранён как control;
**нет нового сброса пропорций или переделки понравившегося лица**.

## Форма: ограниченная доводка

[Эталон / R2 / R3](../studio/reviews/mom-head-form-r3/comparison-identity.png) ·
[R2/R3 в трёх одинаковых ракурсах](../studio/reviews/mom-head-form-r3/comparison-clay.png).

Изменены только три authored targets: две cupid peaks на−1.2mm поZ и внешний
upper-lip/philtrum border на−0.7mm. Остальные targets, jaw/chin/nose/eyes и brow
curve неизменны. Поле пересчитывается на source, а не добавляется поверх R2.
Actual Basis difference R2/R3 проверяется <2mm; это ограничение регрессии, не
likeness score. Верхний рельеф губ мягче; переходы ещё требуют sculpt review.

## Найдена причина прежнего перекоса улыбки

[Actual R2 / R3 balanced pose](../studio/reviews/mom-head-form-r3/comparison-smile.png) ·
[Та же проблема на исходной Rain](../studio/reviews/mom-head-form-r3/source-smile-diagnosis.png).

Предыдущий generic solver выбирал любой канал с ближайшим численным значением
`Smile`. У source оба канала входят в Smile, но одновременно управляют другими
ключами. Поэтому одинаковый Smile не означает одинаковую позу!

| Контроллерный вход | Smile | LipsWide | LipsUp |
|---|---:|---:|---:|
| Left Z≈.0075 | .6 | .15 | 0 |
| Right Y≈.015 | .6 | 0 | .6 |
| Common Z на обеих сторонах | .6/.6 | .15/.15 | 0/0 |
| Отдельная balanced closed-mouth pose | .6/.6 | .075/.075 | .3/.3 |

Это **воспроизведено на неизменённой source geometry**. Нельзя было исправлять
челюсть/губы для компенсации ошибки постановки контроллеров. Исторический solver
и ошибочные кадры не переписаны. Новый `mom_face_controls.py` калибрует одну
выбранную ось с обеих сторон и читает оба ключа **после обоих commits**.
`mom_smile_pose_r3.py` отдельно задаёт LipsUp поY, затем Smile поZ, сохраняет
прочие каналы и проверяет конечные Smile/LipsUp/LipsWide слева и справа.

На509однозначных mirrored mouth pairs mean displacement asymmetry исходного
mixed test≈5.75mm, common-Z≈.0085mm; у R3≈.0088mm. Это диагностика каналов,
**не процент сходства и не художественная оценка**. Просмотр actual balanced
frame подтверждает исчезновение прежнего сильного одностороннего перекоса.
Один closed-mouth smile не заменяет полный facial acting/lip-sync pass.

## Моргание: точная граница того, что выяснено

Source70/30 снова даёт problematic lid/lash frame. Driver `EyelidsClose = -25Y`
от ACT-Eyelid_Upper приY=-.028 даёт **0.7**, не1.0. Значение amplitude=1 в старом
helper обозначало весь authored70/30вход, а не доказанное полное закрытие.

Это не единственная возможная причина: исторический upper-only источник также
имеет плохой lash contour. Сейчас blink **не исправлен и не принят**. Нельзя
просто назвать старую позу full blink или менять понравившуюся eye geometry.
Следующий разбор — реальная ACT/MSTR/ROT/DEF цепь, Action constraints, их
binding/slots и runtime compatibility, затем paired source/candidate poses.

В reopen receipt записан реальный control graph: ACT upper parent MSTR-Eye;
MSTR-Eyering upper связан Action_Eyebrows, lower — Action_Lips_UpDown и другими
actions. LipsUp поY действительно влияет не только на один mouth key. Этот graph
— основание для следующего шага, **не подтверждение гипотезы о сломанном slot**.

## Native evidence и сохранённый файл

- Implementation4178e5d/7275b17 → [build41703583542](https://github.com/PandaGarry/docuflow/actions/runs/41703583542)
  success → actual frames57e9000. Sixcandidate frames +3paired source frames.
- [Packed editable R3 artifact](https://github.com/PandaGarry/docuflow/actions/runs/41703583542/artifacts/13265372165),
  71,293,677bytes, expires2026-11-17T19:33:52Z. Native file внутри архива:
  `.cache/rain-v3/mom-head-form-r3.blend` (скрытый каталог `.cache`).
- [Reopen/pose41704930106](https://github.com/PandaGarry/docuflow/actions/runs/41704930106)
  success → publisheded28afa: скачан реальный uploaded binary, SHA совпал;
  Basis/evaluated neutral errors=0m; все17dependencies packed; reopened neutral
  pixels identical (RGB MAE=0), warm-pose neutral restore=0m. Scripts embedded OFF.
- [Native report](../studio/reviews/mom-head-form-r3/report.json) ·
  [reopen + final pose keys + graph](../studio/reviews/mom-head-form-r3/reopen/verification.json) ·
  [visual review](../studio/reviews/mom-head-form-r3/visual-review.json).

Архив открывается в neutral head-study state. Balanced pose — отдельный
reproducible helper и actual render, не записанная по умолчанию анимация в файле.
Source body/hair сохранены, но скрыты; они не стали новым groom/wardrobe.
Rest/weights/topology/25head key blocks и eye coordinates сохранены; original
spine invalid остаётся. Полная facial migration/acting и hair/body/lookdev
по-прежнему открыты. Art/production swap не включены.

## Проверки

315local tests: предыдущие306 +4paired-policy/refinement +5native result checks.
Проверены frozen recipes/image hashes, source/candidate response, сохранение
R2targets, topology/weights/key names, reopened binary, pose readback/restore.
Это не anatomical/cinema/likeness certification. Private images не читаются и
не публикуются; masters неизменны. Source/A1–A7/R1/R2 и их failures сохранены.

Credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**. Modified,
CC BY4.0 <https://creativecommons.org/licenses/by/4.0/>. No endorsement implied.
