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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("укажи персонажа: dad / mom / son")
    key = sys.argv[1]
    man = pl.build_manifest(key)
    print(f"{key}: поз {len(man['poses'])}/{len(ch.POSES)}, "
          f"эмоций {len(man['emotions'])}/{len(ch.EMOTIONS)}, "
          f"виземов {len(man['visemes'])}/{len(ch.VISEMES)}")
    lib = pl.Library(key)
    miss = lib.missing()
    for kind, items in miss.items():
        if items:
            print(f"  нет {kind}: {', '.join(items)}")
    if "--sheet" in sys.argv:
        print("лист:", pl.contact_sheet(key))
