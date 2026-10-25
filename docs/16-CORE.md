# 16 · Ядро студии: персонажи, позы, эмоции, одежда

Этот документ — карта ядра. Он про то, **как менять персонажей и сцены, не трогая
код**, и как всем этим пользоваться из скриптов.

Коротко: всё, что можно захотеть поменять (поза, эмоция, вещь одежды, причёска,
комплект, пропорции, лицо), лежит в JSON. Код читает эти файлы и не содержит
зашитых имён и цветов.

---

## 1. Из чего состоит ядро

| Файл | Роль | Что внутри |
|------|------|-----------|
| `studio/characters/<id>/character.json` | **личность персонажа** | пропорции, лицо, причёска, гардероб, запреты, голос |
| `studio/library/rigs.json` | скелеты | кости, rest-позы, длины, ширины |
| `studio/library/poses.json` | **27 поз** (26 + зеркальная `wave_left`) | отклонения углов от rest + англ. описание для промпта |
| `studio/library/expressions.json` | **28 эмоций + 9 визем** | 20 числовых параметров лица и их диапазоны |
| `studio/library/wardrobe.json` | **27 вещей** | слоты, вещи: промпт + параметры процедурной отрисовки |
| `studio/library/hairstyles.json` | причёски и бороды | промпт + форма для отрисовки |
| `studio/engine/library.py` | доступ к библиотекам | загрузка, разрешение ссылок, валидация |
| `studio/engine/face.py` | **лицо как параметры** | эмоции, смешивание, виземы, липсинк, микромимика |
| `studio/engine/rig.py` | скелет и движение | FK, IK (руки/ноги), позы, зеркало, пружины, кривые |
| `studio/engine/kit.py` | **персонаж и промпты** | схема, промпт-сборка, ключи ассетов, устаревание, CLI |
| `studio/engine/puppet.py` | **процедурная кукла** | кадр персонажа из JSON: поза + эмоция + одежда |
| `studio/engine/scene.py` | **сцены как данные** | несколько персонажей, камера, реплики, субтитры → кадры → mp4 |
| `studio/scenes/*.json` | сценарии кадров | актёры, позы/эмоции по времени, реплики, камера |
| `studio/engine/artgen.py` | арт-пайплайн | нарезка мастеров, хромакей, реестр, проверка |
| `studio/engine/selftest.py` | тесты ядра | 36 проверок за ~0.4 с |
| `studio/tools/migrate_repo.sh` | переезд репозитория | `filter-branch` фото из истории + проверка + push |
| `studio/engine/bench.py` | бюджеты производительности | мс на кадр/позу/липсинк + точность IK (`--assert`) |
| `studio/engine/core_demo.py` | демо-ролик ядра | позы + эмоции + липсинк + вторичная анимация → mp4 |

### Поток данных

```
character.json + library/*.json
        │
        ├── kit.build_prompt ──────────► генерация арта (мастера в референсах)
        │                                 └── artgen.py → нарезка → QA → реестр
        │
        ├── rig.build_humanoid ──► скелет с нужным ростом в головах
        │        └── apply_pose / hand_ik / look_at / mirror
        │
        ├── face.Face ──────────► параметры лица (эмоция + визема + мигание)
        │
        ├── puppet.Painter ─────► кадр: персонаж в позе, с эмоцией, в одежде
        │                          └── core_demo.py → mp4
        │
        └── scene.still/render ─► сцена: N персонажей + камера + субтитры → mp4
```

---

## 2. Быстрый старт по сценариям

### «Хочу посмотреть персонажа в другой позе»

```bash
python studio/engine/puppet.py preview --char dad --pose think --expr smirk
# → studio/out/puppet-dad-think-smirk.png
```

Мгновенно, без генерации, лицо то же — потому что это один и тот же JSON.

### «Хочу сменить одежду»

```bash
# 1) посмотреть, как выглядит другой комплект (секунды, без генерации)
python studio/engine/puppet.py preview --char dad --top shirt_blue --bottom trousers_dark

# 2) сделать комплект постоянным
python studio/engine/kit.py wear dad --set work --top shirt_blue --bottom trousers_dark --shoes boots_black

# 3) увидеть, какие готовые ассеты теперь устарели
python studio/engine/kit.py stale
```

`kit.py wear` меняет `wardrobe.sets`, пересчитывает отпечаток внешности и печатает
список ассетов, которые надо перегенерировать (у них изменился ключ).

### «Хочу новую позу»

Дописать объект в `studio/library/poses.json`:

```json
"lean_on_wall": {
  "label": "Опирается на стену",
  "tags": ["pose", "street"],
  "prompt": "leaning back against a wall, one foot crossed over the other",
  "bones": {"upper_arm.r": -12, "forearm.r": -46, "spine": -6, "head": -3}
}
```

`bones` — отклонения от rest-позы в градусах (0 = вправо, +90 = вниз).
Проверить: `python studio/engine/library.py` → должно быть «✓ библиотеки в порядке».

Чтобы не считать углы в голове, позу снимают со скелета и сохраняют командой:

```bash
# 1) посмотреть углы текущей позы
python -c "import sys; sys.path.insert(0,'studio/engine'); import rig as R; sk=R.apply_pose(R.build_humanoid(6.0),'wave'); print(sk.capture())"

# 2) сохранить новую позу (проверяются id, имена костей, диапазон углов)
python studio/engine/kit.py pose-save lean_wall --bones "spine:-6,head:-3,upper_arm.r:-12,forearm.r:-46" \
    --root "0,0.05" --label "Опирается на стену" --tags pose,street

# 3) сразу посмотреть, как это выглядит на персонаже
python studio/engine/kit.py pose dad --pose lean_wall --expr smirk --out studio/out/check.png
```

`pose-save` пишет JSON атомарно (`.tmp` + подмена), проверяет углы и кости и
сбрасывает кеш библиотеки — поза доступна в том же процессе и во всех промптах.

**Зеркальные позы.** Вместо второго набора углов пишется одна строка:

```json
"wave_left": {"label": "Машет левой", "mirror_of": "wave", "tags": ["greeting"]}
```

Такая поза считается на скелете (`rig.pose_data`), поэтому отражение точное даже
при несимметричных rest-углах (у ног они разные: 92° и 88°). Свои `bones` у
зеркальной позы указывать нельзя — валидатор это ловит.

### «Хочу новую эмоцию»

Дописать в `studio/library/expressions.json`:

```json
"smug": {"label": "Самодовольный", "face": {"brow_raise": 0.5, "lid": 0.35,
  "smile": 0.35, "mouth_skew": 0.55, "cheek_raise": 0.2}}
```

Параметры лица (`params` в том же файле): `brow_raise`, `brow_angle`,
`brow_pinch`, `eye_open`, `squint`, `lid`, `pupil`, `look_x`, `look_y`,
`mouth_open`, `mouth_wide`, `smile`, `mouth_skew`, `teeth`, `tongue`,
`cheek_raise`, `blush`, `sweat`, `tears`, `nose_wrinkle`.

Одна и та же эмоция работает в двух местах: в кукле (рисуется) и в промпте
(описывается словами) — поэтому арт и превиз не расходятся.

Сохранять эмоции удобнее командой (она проверяет имена параметров и диапазоны):

```bash
python studio/engine/kit.py expr-save smug --label Самодовольный \
    --face "brow_raise=0.5,lid=0.35,smile=0.35,mouth_skew=0.55,cheek_raise=0.2"
python studio/engine/kit.py faces dad --out studio/out/faces.png
```

`--dry-run` в обеих командах проверяет ввод, ничего не записывая.

### «Хочу новую причёску»

`studio/library/hairstyles.json` → `styles`. Меняется у персонажа:

```bash
python studio/engine/kit.py hair dad --style buzz --color "#3A2A22"
```

⚠️ Причёска меняет силуэт головы: после смены перегенерируйте `master/face.png` и
head-ассеты, затем `qa.py`. Это единственная правка, которая не «бесплатна».

### «Хочу нового персонажа»

```bash
python studio/engine/kit.py new uncle --label Дядя --from dad --height 6.3
```

Создаст `studio/characters/uncle/character.json` (пропорции, гардероб и запреты
наследуются от шаблона). Дальше:

```bash
# 1) сгенерировать master/turnaround.png и master/face.png по промпту:
python studio/engine/kit.py prompt uncle --pose idle --expr neutral --camera full
python studio/engine/kit.py prompt uncle --pose idle --expr neutral --camera close

# 2) нарезать, вырезать, обновить реестр, проверить
python studio/engine/artgen.py slice
python studio/engine/artgen.py cut
python studio/engine/artgen.py registry
python studio/engine/artgen.py verify

# 3) посмотреть куклу — до всякой генерации
python studio/engine/kit.py sheet uncle
```

### «Хочу промпт под конкретную сцену»

```bash
python studio/engine/kit.py prompt mom --pose scold --expr anger --camera full --set kitchen
python studio/engine/kit.py plan mom --poses idle,scold --exprs calm,anger --write
```

`plan --write` положит `studio/out/plans/plan-mom.json` — список ассетов с
ключами и промптами; удобно отдавать в пакетную генерацию.

### «Хочу поменять библиотеку из кода» (авторинг)

Все правки идут через `library.py` — он проверяет данные и пишет JSON атомарно
(`.tmp` + `os.replace`), поэтому оборванная запись не оставит битый источник правды:

```python
import library as L

L.save_pose("lean_wall", {"spine": -6, "head": -3},
            root=[0.0, 0.05], label="У стены", tags=["street"], expression="calm")

L.save_expression("smug", {"lid": 0.35, "smile": 0.35, "mouth_skew": 0.55},
                  label="Самодовольный")

L.delete_pose("lean_wall")
```

Что проверяется до записи: id по формату `[a-z0-9_]`, имена костей против профиля
скелета, углы в `-360..360`, `mirror_of` без своих костей, имена параметров лица
против `params` и значения в их `min..max`. Ошибка — исключение, а не «тихо
пропустили».

---

## 2.5. Сцены: серия как данные, а не как скрипт

`scene.py` собирает кадр из нескольких персонажей, ведёт камеру и субтитры.
Сценарий кадра — JSON (`studio/scenes/*.json`):

```json
{
  "id": "s01e01-shot01", "fps": 24, "size": [540, 960], "background": "studio",
  "shots": [{
    "dur": 3.6, "caption": "Первая коробка не влезла",
    "camera": {"zoom": 1.0, "focus": 0.5, "y": 0.45},
    "actors": [{
      "char": "dad", "x": 0.29, "scale": 0.84, "z": 2, "seed": 3,
      "pose": [["0.0", "idle"], ["0.9", "idle_shift"], ["2.3", "hands_on_hips"]],
      "expr": [["0.0", "calm"], ["1.0", "proud"]],
      "say":  [{"text": "Так. Коробки в машине.", "cps": 13.0},
               {"text": "Всё под контролем!", "cps": 13.0}]
    }]
  }]
}
```

Важные решения:

* **Реплики без `start`** ставятся подряд после предыдущей (+`gap`). Так
  наложение двух фраз невозможно по построению — а если `start` указан вручную
  и фразы пересекаются или не влезают в кадр, `validate` это скажет.
* **Позы — ключи по времени**, между ключами плавный переход (`ease_in_out`).
  На самом ключе поза берётся ровно (проверяется тестом), а не «почти».
* **Липсинк считается из текста**, длина реплики — от числа символов и `cps`.
* **Камера** (`zoom`, `focus`, `y`) применяется после композитинга, субтитры
  рисуются после камеры — иначе наезд срезал бы текст.
* **Кадр детерминирован**: `scene.still(scene, t)` на одинаковых данных даёт
  одинаковые байты (тест).

```bash
python studio/engine/scene.py list                       # что есть
python studio/engine/scene.py info s01e01-shot01         # тайминг и реплики
python studio/engine/scene.py validate                   # все сцены
python studio/engine/scene.py still s01e01-shot01 --t 1.6 --out out/frame.png
python studio/engine/scene.py render s01e01-shot01 --quality preview
```

---

## 3. Пропорции: рост в головах вместо сантиметров

`height_heads` в `character.json` — буквально «сколько голов в росте».
Голова при этом **не масштабируется**, под неё подгоняется тело:

```python
R.build_humanoid(6.5)                     # взрослый
R.build_humanoid(4.6, {"leg": 0.86, "arm": 0.9, "head": 1.2})   # ребёнок
```

Поэтому папа, мама и сын выглядят как разные люди, а не как один персонаж
с разным масштабом. Тест это фиксирует: `stature / head_diameter == height_heads`.

Дополнительно у каждого персонажа есть множители `proportions`: `leg`, `arm`,
`torso`, `head` (влияют на скелет) и `belly` (влияет на силуэт в кукле).

---

## 4. Лицо: почему это отдельный модуль

Перегенерировать арт на каждую эмоцию — дорого и рискованно (лицо «уезжает»).
Поэтому лицо параметрическое:

```python
import face as F
f = F.Face.from_expression("panic")            # готовая эмоция
f = f.with_viseme("A", 0.8)                    # губы говорят, брови на месте
f = f.with_blink(0.0)                          # закрытые глаза
f = f.blend(F.Face.from_expression("sad"), 0.4)  # смесь
```

Таймлайн и липсинк:

```python
tl = F.FaceTimeline.from_expressions([(0.0, "calm"), (1.2, "think"), (2.6, "panic")])
spans = F.lip_sync("Так. Коробки в машине.", start=0.5, duration=2.0)
face = F.face_at(t, timeline=tl, spans=spans, blink=1.0, micro=1.0, seed=7)
```

`micro_face` добавляет 2–4 % дрожания зрачков и бровей — на крупном плане лицо
перестаёт быть маской. `core_demo.py` собирает из этого ролик.

---

## 5. Скелет и движение

```python
sk = R.build_humanoid(6.0)                 # собрать по профилю
R.apply_pose(sk, "wave")                   # поза из библиотеки
R.apply_pose(sk, "breath", weight=0.5, additive=True)   # поверх — дыхание
R.hand_ik(sk, "r", (1.6, -1.4))            # дотянуть кисть до точки
R.foot_ik(sk, "l", (-0.3, 3.4))            # поставить стопу
R.look_at(sk, (0.0, -1.0), weight=0.8, max_deg=25)      # взгляд в собеседника
sk.mirror()                                # отразить позу (математически точно)
sk.capture()                               # снять позу как delta-углы
sk.to_dict() / R.Skeleton.from_dict(d)     # сериализация (для сцен и сохранений)
R.pose_data("wave")                        # поза как данные, с разрешённым mirror_of
R.pose_graph(sk, ["idle", "wave"], k=0.4)  # переход между позами
```

Зеркало работает в мировых углах: `world → π − world`, пары `.r/.l` меняются
местами, локальные углы пересчитываются сверху вниз по порядку костей. Поэтому
отражается и наклон корпуса, и работает на скелете с несимметричными rest-углами;
двойное зеркало возвращает исходную позу с точностью `1e-16`
(`selftest.py`: «двойное зеркало = исходная поза»).

Двухзвенный IK считает позиции локтя и выбирает сторону по полюсному вектору.
Точность измеряется, а не декларируется: `bench.py` проверяет 14 достижимых целей
(худший промах `0.0000 %` длины руки) и 4 недостижимые (отклонение направления
`0.0000°` — рука лежит ровно на линии «плечо → цель», а не «промахивается мимо»).

---

## 6. Промпты и ключи ассетов

Промпт собирается из частей, а не пишется руками:

```
стиль → персонаж (тело + волосы + борода + одежда) → требование идентичности
→ поза → эмоция (словами из параметров) → камера → анти-анатомия
→ запреты персонажа → хромакей
```

Ключ ассета — sha256 от персонажа, одежды, позы, эмоции и камеры:

```python
import kit
spec = kit.load_character("dad")
kit.asset_key(spec, pose="wave", expression="joy")            # '6dd34e2f5957'
kit.asset_key(spec, pose="wave", expression="joy", outfit={"top": "shirt_blue"})
```

Сменили худи на рубашку → все зависящие ассеты помечаются устаревшими
(`kit.py stale`, `artgen.py verify`). Это и есть «корректность» в работе с артом:
ничего не забывается и не перегенерируется вслепую.

---

## 7. Команды одним списком

```bash
# персонажи и библиотеки
python studio/engine/kit.py list [chars|poses|expressions|wardrobe|hair]
python studio/engine/kit.py show dad [--json]
python studio/engine/kit.py validate
python studio/engine/kit.py stale

# одежда и причёска
python studio/engine/kit.py wear dad --set street --top shirt_blue --outer jacket_denim
python studio/engine/kit.py hair mom --style bun

# промпты и планы
python studio/engine/kit.py prompt dad --pose wave --expr joy --camera full
python studio/engine/kit.py plan dad --poses idle,wave --exprs calm,joy --write

# новый персонаж
python studio/engine/kit.py new uncle --label Дядя --from dad --height 6.3

# превиз без генерации
python studio/engine/puppet.py preview --char son --pose wave --expr joy
python studio/engine/kit.py pose son --pose wave --expr joy --out studio/out/frame.png
python studio/engine/kit.py sheet dad       # сетка 6 поз × 6 эмоций
python studio/engine/kit.py faces dad       # крупные планы всех эмоций

# авторинг: позы и эмоции без правки кода
python studio/engine/kit.py pose-save lean_wall --bones "spine:-6,head:-3" --label "У стены"
python studio/engine/kit.py expr-save smug --face "lid=0.35,smile=0.35,mouth_skew=0.55"
python studio/engine/kit.py rig --bones      # профиль скелета + проверка симметрии

# сцены (несколько персонажей, камера, субтитры)
python studio/engine/scene.py list
python studio/engine/scene.py validate
python studio/engine/scene.py render s01e01-shot01 --quality high

# анимация и проверки
python studio/engine/core_demo.py --char dad     # mp4 с позами, эмоциями и липсинком
python studio/engine/selftest.py                 # 36 проверок ядра
python studio/engine/bench.py --assert           # бюджеты времени и точность IK
python studio/engine/artgen.py registry && python studio/engine/artgen.py verify
python studio/engine/qa.py --assets studio/characters
```

---

## 8. Что проверяется автоматически

### `selftest.py` — 36 проверок, ~0.4 с

- **библиотеки:** ссылки, наличие базовых поз/эмоций/вещей, `mirror_of` даёт точное
  зеркало; валидатор ловит битую позу, эмоцию вне диапазона и несимметричный
  rest-скелет (проверка сделана «от обратного»: ломаем данные и ждём ошибку);
- **авторинг:** поза сохраняется, читается из файла, применяется и удаляется;
  мусор (плохой id, неизвестная кость, угол 999°, зеркало со своими костями)
  отклоняется; эмоция проверяется по именам и диапазонам;
- **рост** в головах для 3 значений и влияние пропорций;
- **позы:** `wave` поднимает кисть, `point` вытягивает руку, зеркалирование точное
  (`< 1e-9`), руки меняются местами, двойное зеркало = исходник, наклон корпуса
  отражается;
- **IK:** попадает в цель, `look_at` поворачивает голову, сериализация сохраняет позу;
- **лицо:** эмоции меняют параметры и клампятся в диапазоны, визема не трогает
  брови, липсинк укладывается в длительность без щелей, мигание закрывает глаза;
- **персонажи:** схема, промпты (без двойных отрицаний и русского текста), одежда
  меняет промпт, ключи стабильны и чувствительны к правкам;
- **кукла:** кадр не пустой, одежда реально меняет картинку, хромакей ровный,
  все эмоции дают разные кадры;
- **сцены:** образец валиден, кадр детерминирован, поза на ключе берётся точно,
  между ключами — смесь, реплики не накладываются и не вылезают за кадр,
  валидатор ловит неизвестную позу/персонажа/эмоцию, fps и пустые shots;
- создание нового персонажа с нуля и его удаление.

### `bench.py` — бюджеты и точность

```
операция                     мс   бюджет
✓ skeleton+pose             0.24   2.5
✓ frame 360x640 preview    24.6    60.0
✓ frame 540x960 high      163.5   200.0
✓ prompt                    0.02   1.0
✓ face_at                   0.03   0.3
✓ ik                        0.04   0.25
точность IK: 14 достижимых целей, худший промах 0.0000 % длины руки
недостижимая цель: отклонение направления 0.0000°
```

`bench.py` без `--assert` только печатает числа; с `--assert` падает, если бюджет
нарушен или IK промахнулся больше 0.1 % длины руки. Так «оптимизация» и
«точность» проверяются результатом, а не словами.

Что дало ускорение (в 6 раз на кадре 540×960, 332 → 163 мс):

- световые поля «тень/блик» кешируются по размеру bbox (а не пересчитываются
  через `mgrid` на каждую деталь), контур считается numpy-эрозией вместо
  `MinFilter`, и только на мелких деталях;
- фон (градиент + свет + пол) считается один раз на размер и копируется;
- контактная тень размывается в маленьком прямоугольнике под ногами, а не на
  всём кадре;
- даунсэмплинг суперсэмплинга — `Image.reduce` (box), а не `LANCZOS` на полном
  кадре; результат тот же, что и задумано: ровные края без «звона»;
- `quality` в `RenderOpts` (`preview` ×1 / `high` ×2 / `final` ×3) — превиз
  считается ~25 мс, финал — дороже, но это осознанный выбор, а не случайность.

---

## 9. Границы и что дальше

**Честно:** кукла — это превиз и fallback, а не финальный арт. Финальные кадры
дают мастер-ассеты + генерация, кукла нужна, чтобы за секунды проверить позу,
эмоцию, одежду и тайминг, не тратя генерации.

Следующие шаги, которые ложатся на это ядро без переделок:

1. **timeline.py** — сцены как данные: реплики, позы, эмоции, камера, реквизит.
2. **render.py** — сборка кадра из арт-слоёв (мастера) с ригом и 2.5D-деформацией.
3. **audio.py** — TTS по голосам из `character.json` + музыка + `loudnorm`.
4. **props.py** — реквизит (коробки, паспорт, лампа) как отдельные ассеты с якорями
   к костям (`attach: "hand.r"`).
5. **expressions → арт** — генерация набора рта/глаз по параметрам для крупных
   планов, чтобы липсинк был «нарисованным», а не процедурным.
