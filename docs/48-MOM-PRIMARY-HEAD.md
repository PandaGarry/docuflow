# 48 · Мама: реальная переработка primary head, R1 → R2

2026-11-03. Продолжение [form reset](47-MOM-FORM-RESET.md), не ещё один аудит
неизменённого A7. **Новая геометрия головы действительно создана на исходной
Rain**, с оригинальной topology/rig, не procedural replacement и не новая
сгенерированная картинка. Это работа над головой; не готовый персонаж.

## Что поменялось в методе и самой форме

Источник для головы — **официальная исходная Rain**, не сумма A1–A7 face fields.
Унаследованные расширение щёк/рта и укорачивание низа лица отброшены. Одна
контрольная деформация связана с конкретными original vertex IDs в проверенном
mesh dataset; каждый control имеет имя, source/target XYZ и назначение.

- Перестроено соотношение cheek contour, convex malar volume, jaw и chin.
- Изменены nose bridge/tip/ala volumes, а не только цвет/пиксели носа.
- Поддержаны upper/lower lid arcs вокруг **неизменённых глазных яблок/роговицы**.
- Переработаны lip volumes/corners/philtrum-chin relation, без прежнего blanket
  расширения рта. Проверка actual topology выявила важную ошибку первого прохода.
- Для R2 отдельно авторится более мягкая brow centerline с taper; original mesh
  strips прикрепляются к фактической outward head surface, не висят в воздухе.
- Все25original head key blocks (включая Basis) перенесены через одну карту. Имена/weights/
  topology/rig сохранены; это **не** доказывает готовую мимику после новой формы.

Компактная C2 control cage интерполирует authored targets. Она не строит лицо
из фото, не вычисляет likeness score и сама по себе не делает форму хорошей.
Jacobian/finite/bounds checks нужны только для математических сбоев, не для
приёмки анатомии/внешности. 2D reference — художественное направление, не scan.
Канонические masters и личные файлы не менялись; private images не читаются CI.

## R1: получен, просмотрен, НЕ принят как форма

[Identity / A7 / actual R1](../studio/reviews/mom-head-form-r1/comparison-identity.png) ·
[Три совпадающих clay ракурса](../studio/reviews/mom-head-form-r1/comparison-clay.png) ·
[Visual failures](../studio/reviews/mom-head-form-r1/visual-review.json) ·
[Native receipt](../studio/reviews/mom-head-form-r1/report.json).

- Source/cage code8903503/e7f7d69, native publishac0b09f, reviewfcfbd0d.
- [Actual run41692351109](https://github.com/PandaGarry/docuflow/actions/runs/41692351109)
  success; six768×768 Cycles/AgX frames,24samples,9ACT blink samples.
- [Packed editable R1 .blend artifact](https://github.com/PandaGarry/docuflow/actions/runs/41692351109/artifacts/13257863440),
  70,336,170bytes, expires2026-11-17T18:20:43Z. PNG/recipes остаются в Git.
- 82controls; original head6395vertices/6318faces;25original head keys.

**Визуальная проверка остановила этот проход:** brow frame стал жёстким/
недружелюбным, подбородок излишне длинным/угловатым, lip balance неудачен.
И главное: nearest-world-point не гарантирует visible lip surface — два
центральных lip controls оказались на inward-facing mouth geometry. Координаты
были реальными и воспроизводимыми, но anatomical binding был неправильным.
Это не скрыто в «tests pass»: R1 frames/recipe/receipt сохранены как evidence.

Closed-eye PNG показывает широкие выпуклые lid patches и разрывы lash contour.
**Blink visually FAIL**, несмотря на finite geometry/нулевое neutral restore.
Не называем исходный риг полностью адаптированным: rest/attachment/corrective
migration остаётся отдельной задачей после выработки primary head.

## R2: целевая коррекция по фактическим кадрам R1

Это снова rebuild **из официального source**, не накопление R1 поверх A7.

- Chin/jaw укорочены/смягчены относительно излишне угловатого R1; нижняя часть
  не возвращается к прежнему A7 shortening/cheek ballooning.
- Lip controls перепривязаны к outward-facing surface, проверенной normals;
  верхняя губа/нижний pout и corners изменены независимо.
- Более округлый и выраженный nose tip при сохранении более узких alae.
- Shape-preserving C1 brow curve вместо унаследованного излома; taper и narrower
  tail. Frontmost triangle-ray projection по реальной новой голове сохраняет
  небольшой stand-off, не выбирает hidden/interior surface и не экстраполирует
  туда, где головы нет.

[Identity / A7 / actual R2](../studio/reviews/mom-head-form-r2/comparison-identity.png) ·
[Три совпадающих clay ракурса](../studio/reviews/mom-head-form-r2/comparison-clay.png) ·
[Visual review / blockers](../studio/reviews/mom-head-form-r2/visual-review.json) ·
[Native receipt](../studio/reviews/mom-head-form-r2/report.json).

- Implementation1d23cdc → [actual run41694165082](https://github.com/PandaGarry/docuflow/actions/runs/41694165082)
  success → native publish6a54ee6. Кадры front/three-quarter/profile/blink/smile
  **получены и просмотрены**, не план/stand-in.
- [Packed editable R2 .blend artifact](https://github.com/PandaGarry/docuflow/actions/runs/41694165082/artifacts/13260841171),
  70,319,259bytes, expires2026-11-17T18:33:34Z. Это head study с сохранёнными,
  но скрытыми source body/hair. BlendSHA256
  `138e9c592a01814027783e1a21e541cd2b188f6d400015d0c8af8c407f305b0d`.
- 83controls, source topology/weights/key names/eye coordinates preserved.
  New invalid=[]; original spine invalid сохраняется; neutral restore=0m.
- R2 действительно меняет геометрию. Brow arch мягче R1, chin/jaw менее угловаты,
  lip surface binding исправлен, upper lip contour и nose tip стали выраженнее.
  Но это **не likeness pass**: Cupid contour местами чрезмерен, muzzle/philtrum/
  cheek/lid planes и характер ещё не эталонные. Нет art/user/production approval.

### Acting — явные visual failures, не «прошедшие тесты»

R2 blink всё ещё имеет выпуклые blank lid patches и разрыв lash line. Запрос
симметричной улыбки .6/.6 дал заметную асимметрию рта, хотя записанные per-step
key responses близки к targets. Нужен paired source/candidate разбор полного
ACT/skeletal/corrective ответа; сейчас нельзя честно свести причину к одному
элементу. **Blink и symmetric smile не приняты.** Finite samples не меняют этого.

### Saved binary, а не только render из builder process

Отдельный `mom-head-reopen.yml` скачивает именно artifact41694165082, проверяет
SHA, открывает `.blend` с embedded scripts OFF, проверяет geometry/keys/weights/
rest/packed textures и заново рендерит neutral front. На этом checkpoint проверка
**запущена, результат ещё не получен**. PNG из build сами по себе не доказывают
корректное сохранение/повторное открытие файла.

## Границы результата

Это **нейтральная head-form study**, не новая причёска/skin lookdev/одежда/тело.
Исходные body/hair сохранены, но скрыты в диагностическом `.blend`; scarf
visibility driver muted только для изоляции, pose/shape drivers не выключены.
Не выдавать этот файл за окончательную полную маму с готовым acting.

Source rest сейчас сохранён как технический baseline, не художественный запрет:
после стабилизации формы потребуются осмысленные переносы facial attachments/
rest/controls/correctives. Готовность проверяется визуально и комбинациями поз,
а не сохранением rig signature или количеством unit tests. Hair mass/part/waves
и body/wardrobe идут позже; failed A7 cap/plates не являются production groom.

Original asset credit: **Rain Rig (CC) Blender Foundation | studio.blender.org**.
Modified geometry/controls/diagnostics, CC BY4.0
<https://creativecommons.org/licenses/by/4.0/>. No endorsement implied.


## Воспроизведение и тесты

302 local tests PASS (286 previous +10 cage +6 R2 surface/curve), plan/checklist/
diff checks PASS. Lightweight audit CI сохраняет11stdlib checks, затем ставит
только numpy1.26.4 для16pure geometry tests; не поднимает renderer.

```bash
# Pinned bpy/OS deps: .github/workflows/mom-head-form-r2.yml
python studio/tools/mom_head_form_r2.py
# Public comparison only; uniform eye-anchor transform, no face warp:
python studio/tools/mom_head_form_review_r2.py
```

R1/его ошибки не переписаны; R2 имеет собственные spec/script/frames/receipt и
native artifact. Masters/A1–A7/audit сохранены. Следующий этап остаётся реальная
скульптурная доводка формы и исправление facial migration/диагностик, не beauty
hair/color masking и не переключение production defaults.
