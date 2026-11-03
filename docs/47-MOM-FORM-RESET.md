# 47 · Мама: A7 отклонён по дизайну, остановка косметических итераций

2026-11-03. Пользователь прямо указал: работа недостаточно профессиональная и
точечная, персонаж далёк от эталона **по всем направлениям**, спешка не требуется.
Это не просьба ещё немного сгладить стыки. **A7 отклонён как художественное
направление/результат; требуется существенная переработка**, не polish-only.

## Ошибка предыдущего метода

1. Доминировала форма Rain. Небольшие smooth fields меняли отдельные признаки,
   но не выстраивали узнаваемую голову/характер/силуэт по эталону.
2. Для сравнений использовался увеличенный маленький crop из turnaround, хотя
   в репозитории есть гораздо более подробный `mom/master/face.png` 768×1198.
3. Картинки стояли рядом, но головы не были зарегистрированы даже одинаковым
   масштабом/уровнем глаз. Часть прежних рассуждений о пропорциях была ненадёжна.
4. Косметика/причёска добавлялись до принятия крупных форм. Волосы получились
   набором loft plates поверх cap; швы — симптом неподходящей конструкции,
   а не единственная проблема. Сглаживание этих швов не сделает эталонный groom.
5. Неизменность rig rest стала фактическим ограничителем дизайна. Сохранять
   историю/работоспособность надо, но не ценой запрета нужных изменений формы.
6. Render/CI/test success слишком часто сопровождались подачей как следующего
   художественного шага. Они лишь технические доказательства, не качество.

## Что сделано сейчас (не новый персонаж)

- A7 фиксируется как `rejected_requires_major_rework`, production swap запрещён.
- Сравнение по **high-res identity portrait** и существующему native A7:
  два pupil anchors, только translation/rotation/**uniform** scale. Никакой
  растяжки лица/warp/beauty retouch, маскирующей расхождения.
- Ручные приблизительные landmarks с явной погрешностью и относительными
  расстояниями. Это экранная диагностика, **не** калиброванная 3D-цель/likeness score.
- Whole-character board честно отмечает разные позы (turnaround vs T-pose), а не
  выдаёт это за точное измерение плеч/талии/бедер.
- Новый native diagnostic worker должен показать неизменённые source и A7
  головы без волос/косметики в одинаковых front/three-quarter/profile и экспортировать
  original indexed topology/neutral/weights для точечного редактирования областей.
  Native кадры получены и просмотрены; это прежняя форма, **не новый sculpt**.

[Eye-aligned audit](../studio/reviews/mom-form-audit/eye-aligned-audit.png) ·
[Whole-character audit](../studio/reviews/mom-form-audit/whole-character-audit.png) ·
[Landmarks + uncertainty](../studio/reviews/mom-form-audit/landmarks.json) ·
[Image receipt](../studio/reviews/mom-form-audit/image-audit.json).

После eye alignment экранные признаки показывают, в частности: у A7 шире eye
opening и рот относительно IPD, короче нижний отрезок рот→подбородок. Прежняя
идея «ещё расширить рот/укоротить низ лица» поэтому могла идти в неверную сторону.
Приблизительные ratios: eye opening .64 vs .56, mouth width .79 vs .71,
mouth→chin .40 vs .52 (A7 vs portrait). Есть погрешность ручных picks и различия
проекции/взгляда/мимики: **не задавать такие коэффициенты скульпту вслепую**.
Нос отличается не только шириной: нужен анализ объёма bridge/tip/alar planes.

## Новый порядок работы и художественные стоп-условия

### 1. Reference/design brief

High-res face portrait — основной cartoon identity; turnaround — общий силуэт
и дополнительные views; family art — характер/стиль; реальные фото — локальные
индивидуальные подсказки. Между изображениями есть разные выражения/освещение,
это не идеальный 3D scan. Личные фото не публиковать и не отправлять в CI.

### 2. Primary forms, прежде волос/материалов

Сформулировать крупные объёмы: skull/forehead, face width/height, cheek/jaw/chin,
orbits/lids, nose bridge/tip, muzzle/lip volumes, neck/head relationship.
Редактировать осмысленные mesh regions/anchors, проверять front **и** profile,
не вводить очередные mm-сдвиги по неверно угаданным Gaussian centers.
Проверка clay: если лицо узнаётся как Rain или плоскости не сходятся с эталоном,
нет перехода к beauty hair/material polish. Диагностические кадры не являются
новой формой. Следующий реальный art milestone — переработанная neutral head.

### 3. Secondary forms и rig migration

Согласовать eye globes/lids/corners, nose/nostrils, philtrum/lips/chin в объёме.
При необходимости разрешены versioned изменения rest bones/cage/rig proportions:
неизменность старой rig signature не является художественной целью. Прежний
исходник сохраняется; деформации/correctives должны переноситься и проверяться
на новой форме, а не объявляться готовыми из-за сохранённых названий костей.

### 4. Hair as design, не ремонт старых plates

Сначала coherent scalp/part + крупный силуэт и направление асимметричных волн,
затем слои/локоны/кончики, затем шейдинг. Не ставить новые пряди поверх заведомо
неподходящей основы, не прикрывать провал головы волосами. Текущая конструкция
cap+lofts остаётся rejected experiment, не production groom для бесконечного polish.

### 5. Whole character, surface/wardrobe, acting

Проверить тело/шею/плечи/силуэт в сопоставимой нейтральной позе, затем одежду по
эталону, skin/hair lookdev под нейтральным и целевым светом. Заранее не утверждать,
что все численные размеры тела неправильны: сейчас нет честно зарегистрированного
body comparison. Приоритет «сначала форма, затем одежда» сохраняется.
Blink/smile/head turns и промежуточные кадры, затем речь/динамика/коллизии.

## Что не объявляется достигнутым

Нет A8, новой принятой формы, likeness pass или киноуровня. Следующий этап ещё
предстоит выполнить. Публиковать частые маленькие checkpoints означает сохранять
проверяемую работу, **не** присваивать каждой правке новый статус качества.
Masters, source Rain, A1–A7 recipes/frames и failures сохраняются. Native source
scripts disabled; личные фото остаются ignored/local. Числа/CI не заменяют
видимую форму и художественную/пользовательскую приёмку.


## Полученный native audit и точная граница результата

[Шесть clay views: source слева / существующий A7 справа](../studio/reviews/mom-form-audit/native-v2/native-clay-audit.png) ·
[Native receipt](../studio/reviews/mom-form-audit/native-v2/native-audit.json) ·
[Visual review / priorities](../studio/reviews/mom-form-audit/visual-review.json).

- [Run41670203671](https://github.com/PandaGarry/docuflow/actions/runs/41670203671)
  success, published a955467. bpy4.5/Cycles CPU/AgX, six768×768 frames,24samples.
- [Diagnostic artifact](https://github.com/PandaGarry/docuflow/actions/runs/41670203671/artifacts/13247612447),
  10,757,459bytes, expires2026-11-17T16:05:45Z. Это PNG/JSON, **не новый .blend**;
  исторический A7 .blend остаётся в ссылках документа46.
- Индексированный `head-edit-data.json.gz`:6395vertices/6318polygons, world-space
  Basis и evaluated neutral без subdivision, исходные faces/group weights,
  shape-key names/related rest bones. Payload2.73MB, gzip853KB; CC-BY4 attribution
  внутри. Не target mesh и не скан пользователя. Данные доступны standard
  `gzip.open` + `json.load`, а не только внутри Blender.
- Источник/source hash проверен; topology/group weights/key names соответствуют,
  rest signatures одинаковы, новых invalid drivers нет; original spine invalid
  сохранён. Это проверка соответствия, не необходимость сохранить rest в redesign.
- **Новая геометрия не создана.** Прежняя форма Rain/A7 теперь показана отдельно
  от волос/одежды/skin lookdev, чтобы не маскировать главную проблему.

Первый worker41668827955 успешно рендерил, но не опубликовал из-за нового human
checkpoint; исправлены reconciliation и always-retained artifact. Первый
published audit41669360255/26ed5ad оставил шарф: его hide_render управляется
исходным driver. Старое описание «all wardrobe hidden» **было неточным**.
Результаты сохранены в родительской папке, не перерисованы задним числом.
`native-v2` заглушает только этот visibility driver в disposable diagnostic
scene, не pose/shape drivers; .blend с заглушенным driver не распространяется.
Scarf действительно отсутствует в просмотренных v2 кадрах, geometry payload
byte-identical. **v2 — версия диагностики, не версия нового персонажа.**

### Проверки и воспроизведение

286 local tests PASS (275 existing +8 image audit +3 native receipt integrity),
plan validate/checklist/diff PASS. Отдельный lightweight
`mom-form-contracts.yml` проверяет11audit contracts на clean checkout без bpy,
Pillow или личных файлов; это не native render и не художественная приёмка.

```bash
python -m unittest discover -s studio/tests -p 'test_mom_*.py' -v
# Public-image audit needs Pillow11.3:
python studio/tools/mom_form_review.py
# Native runtime/OS libraries as in .github/workflows/mom-form-audit.yml;
# rebuilds exact source/A7 from pinned official asset; embedded scripts OFF:
python studio/tools/mom_native_form_audit.py
```

Следующий художественный milestone остаётся **реально переработанная голова**,
а не ещё один аудит/счётчик тестов. Текущий checkpoint — исправление метода и
проверенная диагностическая база для неё, не выполнение этого milestone.
