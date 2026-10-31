"""Собрать manifest.json и сводный лист библиотеки.

    python studio/tools/build_manifest.py dad
    python studio/tools/build_manifest.py dad --sheet
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import characters as ch
import poselib as pl

GROUPS = {
    "view": "Ракурсы", "idle": "Стойки", "gesture": "Жесты",
    "walk": "Ходьба (профиль)", "run": "Бег (профиль)", "daily": "Быт",
}

PROG = HERE.parents[2] / "docs" / "25-PROGRESS.md"


def write_progress(keys: list[str]) -> Path:
    """Журнал прогресса библиотеки: что готово, что нет, по каждому персонажу."""
    import datetime
    import poselib as pl

    lines = ["# Прогресс библиотеки кадров", "",
             f"_обновлено: {datetime.date.today().isoformat()}_",
             "", "Файл пересобирается командой "
             "`python studio/tools/build_manifest.py <персонаж> --progress`.",
             ""]
    total_done = total_all = 0
    for key in keys:
        char = ch.CHARACTERS[key]
        lib = pl.Library(key)
        man = lib.manifest
        done_p = len(man.get("poses", {}))
        emo = man.get("emotions", {})
        vis = man.get("visemes", {})
        done_e = sum(len(v) for v in emo.values())
        done_v = sum(len(v) for v in vis.values())
        face_views = [v for v in ch.VIEWS if v != "back"]
        total_done += done_p + done_e + done_v
        total_all += (len(ch.POSES) + len(ch.EMOTIONS) * len(face_views)
                      + len(ch.VISEMES) * len(face_views))
        lines.append(f"## {char.name} (`{key}`) — "
                     f"{done_p + done_e + done_v}/"
                     f"{len(ch.POSES) + len(ch.EMOTIONS) + len(ch.VISEMES)} кадров")
        lines.append("")
        lines.append(f"позы {done_p}/{len(ch.POSES)} · "
                     f"эмоции {done_e}/{len(ch.EMOTIONS) * len(face_views)} · "
                     f"виземы {done_v}/{len(ch.VISEMES) * len(face_views)}")
        lines.append("")
        for g, title in GROUPS.items():
            items = [p for p in ch.POSES if p.group == g]
            if not items:
                continue
            marks = " ".join(("x" if p.key in man.get("poses", {}) else " ")
                             for p in items)
            names = ", ".join(
                (f"**{p.key}**" if p.key in man.get("poses", {}) else p.key)
                for p in items)
            lines.append(f"- [{'x' if all(p.key in man.get('poses', {}) for p in items) else ' '}]"
                         f" **{title}** [{marks}] — {names}")
        for kind, items, label in (("emotions", ch.EMOTIONS, "Эмоции"),
                                   ("visemes", ch.VISEMES, "Виземы")):
            for view in face_views:
                have = man.get(kind, {}).get(view, {})
                names = ", ".join(f"**{i}**" if i in have else i for i in items)
                lines.append(
                    f"- [{'x' if len(have) == len(items) else ' '}] **{label}** "
                    f"({view}) [{len(have)}/{len(items)}] — {names}")
        lines.append("")
    lines.append(f"**Всего: {total_done}/{total_all} кадров.**")
    PROG.write_text("\n".join(lines) + "\n")
    return PROG


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("укажи персонажа: dad / mom / son")
    key = sys.argv[1]
    man = pl.build_manifest(key)
    emo = {v: len(d) for v, d in man["emotions"].items()}
    vis = {v: len(d) for v, d in man["visemes"].items()}
    print(f"{key}: поз {len(man['poses'])}/{len(ch.POSES)}")
    print(f"  эмоции по ракурсам: {emo}")
    print(f"  виземы по ракурсам: {vis}")
    lib = pl.Library(key)
    miss = lib.missing()
    for kind, items in miss.items():
        if items:
            print(f"  нет {kind}: {', '.join(items)}")
    if "--sheet" in sys.argv:
        print("лист:", pl.contact_sheet(key))
    if "--progress" in sys.argv:
        print("прогресс:", write_progress([key]))
