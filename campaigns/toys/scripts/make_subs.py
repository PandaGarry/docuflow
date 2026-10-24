"""Субтитры .srt по репликам из timeline.py.

Запуск: python scripts/make_subs.py -> out/toys-cleanup.srt
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as tl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stamp(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    lines = []
    starts = [it["start"] for it in tl.VO]
    for i, item in enumerate(tl.VO, start=1):
        start = item["start"] - 0.12
        end = item["start"] + item["dur"] + 0.45
        if i < len(tl.VO):
            end = min(end, starts[i] - 0.08)
        lines.append(f"{i}\n{stamp(start)} --> {stamp(end)}\n{item['text']}\n")
    # финальный призыв как отдельный титр
    lines.append(f"{len(tl.VO) + 1}\n{stamp(31.2)} --> {stamp(33.4)}\n"
                 "Подпишись, пока мама убирает\n")
    out = os.path.join(HERE, "out", "toys-cleanup.srt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("✓", out)


if __name__ == "__main__":
    main()
