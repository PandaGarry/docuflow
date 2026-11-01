"""Новый костюм персонажа: отдельная папка кадров и готовые промпты.

    python studio/tools/new_outfit.py dad shirt
    python studio/tools/new_outfit.py dad shirt --poses wave,point,idle

Зачем
-----
Одежда меняется, а библиотека кадров — сотня картинок. Перегенерировать её
под каждый костюм дорого и опасно: телосложение снова разъедется.

Поэтому костюм — отдельный набор кадров (`studio/2p5d/dad-shirt/`), который
собирается только из того, что нужно конкретной серии. Этот скрипт:

1. создаёт папку костюма и кладёт туда разметку лица из канона (рамка та же —
   разметка переносится);
2. пишет `pack.json`: какие кадры нужны и какие промпты их делать;
3. печатает порядок работы: сначала мастер ракурса по референсу канона,
   дальше все кадры — по референсу нового мастера.

Стоимость нового костюма: 1–3 мастера + портреты нужных ракурсов + только
те позы, что есть в сцене. Мимика и виземы НЕ перегенерируются: они
собираются слоями поверх нового портрета (facefx), как и в каноне.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import characters as ch

ROOT = HERE.parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("char", nargs="?", default="dad")
    ap.add_argument("outfit")
    ap.add_argument("--poses", default="",
                    help="через запятую: какие позы нужны этой серии")
    a = ap.parse_args()

    base = {"dad": ch.DAD, "mom": ch.MOM, "son": ch.SON}[a.char]
    try:
        char = ch.dressed(a.char, a.outfit)
    except KeyError as e:
        print(e)
        return 1

    d = char.dir
    d.mkdir(parents=True, exist_ok=True)
    for name in ("emotions", "visemes", "poses"):
        (d / name).mkdir(exist_ok=True)
    for name in ch.VIEWS[:3]:
        (d / "emotions" / name).mkdir(parents=True, exist_ok=True)
        (d / "visemes" / name).mkdir(parents=True, exist_ok=True)

    # Разметка лица переносится из канона: рамка портрета та же.
    src_face = base.dir / "face.json"
    if src_face.exists() and not (d / "face.json").exists():
        shutil.copy(src_face, d / "face.json")

    poses = [p.strip() for p in a.poses.split(",") if p.strip()]
    pack = {
        "char": a.char,
        "outfit": a.outfit,
        "outfit_prompt": char.outfit,
        "masters": {},
        "poses": poses,
        "note": "Кадры делаются правкой референса: сначала мастер, потом кадры.",
    }
    for view, name in ch.VIEW_MASTERS.items():
        if view == "back":
            continue
        pack["masters"][view] = {
            "file": str(d / name),
            "reference": str(base.dir / name),
            "prompt": (
                "Keep this exact character: same face, same hair, same beard, same "
                "body build and proportions, same head size, same soft studio "
                f"lighting, same flat chroma-key green background. Change ONLY the "
                f"clothes: {char.outfit}. Same pose, same framing, full body visible "
                "from hair to shoes."
            ),
        }
    (d / "pack.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1) + "\n")

    print(f"папка: {d}")
    print(f"костюм: {char.outfit}\n")
    print("1) мастера ракурсов — по одному кадру, референс — канон:")
    for view, m in pack["masters"].items():
        print(f"   {view:14s} ref={Path(m['reference']).name}")
    print("\n2) портреты ракурсов (для мимики и виземов) — от нового мастера:")
    for view in ("front", "three-quarter", "side"):
        print(f"   {view:14s} → {d / 'emotions'/ view / 'neutral.png'}")
    print("\n3) позы этой серии:", ", ".join(poses) if poses else "(не заданы)")
    print("\nМимика и виземы не перегенерируются — они собираются слоями "
          "поверх нового портрета (facefx).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
