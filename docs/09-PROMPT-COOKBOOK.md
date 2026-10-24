# 09 · Промпт-кулинарная книга

Правила, которые дают **предсказуемый** арт: одного героя, без лишних рук и без
«съехавшего» лица между кадрами.

## Три правила, которые решают 90 % брака

1. **Один герой = один шаблон + один референс.** Никогда не «переписываем»
   промпт героя по памяти: берём шаблон из `studio/tools/prompts/` и меняем
   только позу/эмоцию/ракурс.
2. **Референсы всегда идут тройкой:** реальное фото (для сходства) +
   turnaround-лист (для стиля) + предыдущая удачная поза (для консистентности).
3. **Анатомия проговаривается явно.** «Ровно две руки, две ноги, пять пальцев
   на открытой ладони, один рот, два глаза» — не лишняя строка, а страховка.

## Структура промпта

```
[СТИЛЬ] + [ГЕРОЙ: постоянные признаки] + [ПОЗА/ЭМОЦИЯ] + [КАДР] +
[АНАТОМИЯ] + [ФОН] + [ТЕХНИКА]
```

Порядок не случайный: модель сильнее всего слушает начало и конец промпта,
поэтому стиль — в начале, технические ограничения — в конце.

## Шаблон: герой (на примере папы)

```
Modern flat 2D cartoon character, premium TV-animation style, bold dark-brown
outlines, flat colors with one cel-shadow, big expressive eyes.
DAD: stocky build, 6.5 heads tall, short dark-brown hair with shaved faded
sides and a spiky top, full neat dark beard and mustache, thick eyebrows,
warm brown eyes, light-gray crewneck sweatshirt, dark jeans, brown sneakers.
POSE: hands on hips, chest out, self-satisfied smirk, eyebrow raised.
Full body, front view, facing camera.
ANATOMY: exactly two arms, two legs, one head, two eyes, five fingers per hand,
no extra limbs, no floating objects.
BACKGROUND: perfectly flat chroma key green (#00B140), no shadows, no text.
```

## Шаблон: turnaround-лист (один раз на героя)

```
Character turnaround sheet, four views in a row: front, three-quarter,
profile, back. Same character, same clothes, same proportions in all views.
[ГЕРОЙ как выше] Standing relaxed A-pose, arms slightly away from the body.
Flat chroma key green background, no shadows, no text, no props, no logos.
```

> Turnaround — это **главный** ассет героя: он используется как референс для
> всех поз. Делать его первым, проверять по QA, только потом генерировать позы.

## Шаблон: поза (генерируется с turnaround в референсах)

```
[ГЕРОЙ] POSITION: [описание позы]. EXPRESSION: [эмоция, брови, рот].
CAMERA: [фронт / 3-4 / профиль / крупный план], full body.
ANATOMY: exactly two arms, two legs, five fingers per open palm, no extra limbs.
[ФОН: зелёный / сцена]
```

## Негативные ограничения (вставлять всегда)

```
no extra limbs, no extra fingers, no duplicate hands, no merged fingers,
no text, no watermark, no logo, no signature, no busy background,
no gradients on skin, no realistic rendering, no photographic look,
no props not mentioned, no hats/hair changes, no different clothes
```

## Типовые ошибки и лечение

| Симптом | Причина | Что делать |
|---------|---------|-----------|
| Третья рука | промпт перегружен позой + реквизитом | убрать реквизит из промпта, генерировать отдельно и клеить в движке |
| Меняется причёска/борода | нет референса героя | добавить turnaround + фото в референсы |
| Другой стиль линии | стиль описан в середине промпта | перенести стиль в первые 20 слов |
| «Мусорные» буквы на одежде | модель любит дописывать текст | явный `no text`, тексты рисуем сами поверх |
| Мыльные края | генерируется сразу в нужном размере | генерировать с запасом 1.5×, уменьшать LANCZOS |
| Другая палитра | нет фиксации цветов | вписать HEX-коды в промпт (в библии они есть) |
| «Фотореализм» просачивается | стиль сформулирован слабо | добавить «flat vector, bold outline, two-tone shading» |

## Консистентность между сериями: практика

1. Храните **«золотой набор»**: turnaround + 3 удачные позы на героя. Все
   новые позы генерируются с ними в референсах.
2. Храните **удачные сиды**, если модель их поддерживает: повторяемость важнее
   «случайной красивой генерации».
3. Проверяйте палитру после каждой генерации (`engine/qa.py`): ΔE к эталону.
4. Одна серия — один набор фонов. Не смешивайте «гостиную из серии 2» и
   «гостиную из серии 7»: мебель поедет, зритель заметит.

## Реквизит и фоны (короткие шаблоны)

```
PROP: a cardboard moving box, cartoon style, bold outline, flat colors,
slightly dented, packing tape across the top. Isolated on chroma key green.
```
```
BACKGROUND: cozy cartoon living room, cream walls with sage wainscot, mustard
sofa, low shelf with baskets, patterned coral rug, window with daylight,
15% overscan on all sides, no characters, no text.
```

## Что мы никогда не просим у модели

- Нарисовать одного героя «в двух позах на одном листе» — анатомия ломается.
- Дорисовать текст/надписи — это всегда наш слой.
- Сделать «как в мультфильме X» — юридически рискованно и стилистически
  размыто; вместо этого описываем признаки (линия, палитра, пропорции).
