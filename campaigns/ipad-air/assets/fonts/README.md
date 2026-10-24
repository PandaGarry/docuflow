# Шрифты

Используется **Montserrat** (SIL Open Font License 1.1, см. `OFL.txt`).

Пакеты `@fontsource/montserrat` поставляются раздельно по подмножествам
(латиница и кириллица — разные файлы), а для титров нужен один шрифт,
покрывающий обе раскладки. Поэтому подмножества 300–900 сведены в один файл
на начертание:

```bash
npm pack @fontsource/montserrat          # или npm install @fontsource/montserrat
python - <<'PY'
from fontTools.merge import Merger
for w in [300, 400, 500, 600, 700, 800, 900]:
    Merger().merge([f"montserrat-latin-{w}-normal.woff2",
                    f"montserrat-cyrillic-{w}-normal.woff2"]).save(f"Montserrat-{w}.ttf")
PY
```

`Montserrat-300.ttf` … `Montserrat-900.ttf` — готовые сведённые начертания,
их и читает `scripts/render.py`. Трекинг и размеры подбираются в коде.
