"""Разбор референс-роликов: кадры, монтаж, движение, кадрирование, палитра.

Зачем
-----
Перед тем как строить персонажа и анимацию, нужен эталон, разложенный на числа:
как часто режут, сколько длится план, сколько в кадре движения, как крупно
стоит персонаж, из каких цветов собрана картинка. Иначе «сделай как у людей»
превращается в угадывание.

Что делает
----------
1. читает mp4/webm/mov через ffmpeg (он уже есть в imageio_ffmpeg);
2. режет на кадры с заданной частотой и собирает контактные листы;
3. ищет склейки (резкий скачок разницы кадров), считает длину планов;
4. считает «энергию движения» по секундам — это темп анимации;
5. оценивает кадрирование: какую долю высоты кадра занимает персонаж;
6. собирает палитру (топ цветов) и среднюю яркость;
7. пишет markdown-отчёт рядом с роликом.

Запуск
------
    python studio/tools/ref_analyze.py studio/reference/*.mp4
    python studio/tools/ref_analyze.py studio/reference/a.mp4 --fps 6 --out docs/18-REFERENCE.md
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "engine"))


def ffmpeg() -> str:
    from imageio_ffmpeg import get_ffmpeg_exe
    return get_ffmpeg_exe()


def probe(path: str) -> dict:
    """Длительность, размер, fps — из stderr ffmpeg (без внешних зависимостей)."""
    out = subprocess.run([ffmpeg(), "-hide_banner", "-i", path],
                         capture_output=True, text=True).stderr
    info = {"path": path, "duration": 0.0, "size": (0, 0), "fps": 0.0}
    for line in out.splitlines():
        if "Duration:" in line:
            hms = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = hms.split(":")
            info["duration"] = int(h) * 3600 + int(m) * 60 + float(s)
        if "Video:" in line and "x" in line:
            for tok in line.split(","):
                tok = tok.strip()
                if "x" in tok and tok.replace("x", "").isdigit():
                    w, h = tok.split("x")
                    info["size"] = (int(w), int(h))
                    break
            if " fps" in line:
                for tok in line.split():
                    if tok.replace(".", "").replace("fps", "").isdigit() and "fps" in line:
                        pass
            import re
            m = re.search(r"([\d.]+) fps", line)
            if m:
                info["fps"] = float(m.group(1))
    return info


def extract_frames(path: str, fps: float, outdir: str) -> list[str]:
    os.makedirs(outdir, exist_ok=True)
    pattern = os.path.join(outdir, "f_%05d.png")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", path,
                    "-vf", f"fps={fps},scale=360:-2", pattern], check=True)
    return sorted(glob.glob(os.path.join(outdir, "f_*.png")))


def frame_array(path: str) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), np.float32)


def contact_sheet(frames: list[str], out: str, cols: int = 5, thumb: int = 200) -> str:
    from PIL import Image, ImageDraw
    if not frames:
        return ""
    ims = [Image.open(f).convert("RGB") for f in frames]
    h = int(thumb * ims[0].height / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb, rows * h), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        x, y = (i % cols) * thumb, (i // cols) * h
        sheet.paste(im.resize((thumb, h)), (x, y))
        d.rectangle([x, y, x + thumb - 1, y + h - 1], outline=(210, 200, 190))
    sheet.save(out)
    return out


def analyze(path: str, fps: float = 6.0, workdir: str | None = None) -> dict:
    info = probe(path)
    tmp = workdir or tempfile.mkdtemp(prefix="ref_")
    frames = extract_frames(path, fps, tmp)
    if len(frames) < 4:
        raise RuntimeError(f"{path}: не удалось вытащить кадры")
    arrs = [frame_array(f) for f in frames]
    h, w = arrs[0].shape[:2]
    prev = arrs[0]
    diff = []
    for cur in arrs[1:]:
        diff.append(float(np.abs(cur - prev).mean()))
        prev = cur
    diff = np.array(diff)
    cuts = [i for i, d in enumerate(diff) if d > max(np.median(diff) * 4.5, 12.0)]
    # энергия движения по секундам
    per_sec: list[float] = []
    step = max(int(round(fps)), 1)
    for i in range(0, len(diff), step):
        chunk = diff[i:i + step]
        per_sec.append(round(float(chunk.mean()) if len(chunk) else 0.0, 2))
    # кадрирование: доля высоты, занятая «не-фоном»
    subj_h, subj_cy = [], []
    for a in arrs[::max(len(arrs) // 12, 1)]:
        bg = np.median(a.reshape(-1, 3), axis=0)
        mask = (np.abs(a - bg).sum(axis=2) > 60)
        rows = np.nonzero(mask.any(axis=1))[0]
        if len(rows) > 10:
            subj_h.append(round(float((rows.max() - rows.min()) / a.shape[0]), 2))
            subj_cy.append(round(float((rows.min() + rows.max()) / 2 / a.shape[0]), 2))
    # палитра
    allpx = np.concatenate([a.reshape(-1, 3)[::37] for a in arrs])
    q = (allpx // 32 * 32).astype(int)
    uniq, counts = np.unique(q, axis=0, return_counts=True)
    order = np.argsort(-counts)[:8]
    palette = [{"rgb": [int(v) for v in uniq[i]], "share": round(float(counts[i] / counts.sum()), 3)}
               for i in order]
    sheet = contact_sheet(frames[::max(len(frames) // 20, 1)],
                          os.path.splitext(path)[0] + "-sheet.png")
    return {
        "path": path, "duration": round(info["duration"], 2), "size": info["size"],
        "fps": info["fps"], "frames_analyzed": len(frames),
        "shot_cuts": len(cuts),
        "avg_shot_len": round(info["duration"] / max(len(cuts) + 1, 1), 2),
        "motion_per_sec": per_sec,
        "motion_avg": round(float(diff.mean()), 2),
        "subject_height_ratio": subj_h, "subject_center_y": subj_cy,
        "palette": palette, "sheet": sheet,
    }


def report(results: list[dict], out: str | None = None) -> str:
    lines = ["# P0. Разбор референсов", "",
             "Считается `studio/tools/ref_analyze.py` из файлов в `studio/reference/`.",
             "Числа — не «красиво/некрасиво», а параметры, которые надо повторить.", ""]
    for r in results:
        lines += [f"## {os.path.basename(r['path'])}", "",
                  f"- длительность: **{r['duration']} с**, кадр {r['size'][0]}×{r['size'][1]}, "
                  f"{r['fps']} fps",
                  f"- склеек: **{r['shot_cuts']}**, средний план **{r['avg_shot_len']} с**",
                  f"- энергия движения (средняя разница кадров): **{r['motion_avg']}**",
                  f"  по секундам: {r['motion_per_sec']}",
                  f"- крупность: высота персонажа = "
                  f"{r['subject_height_ratio']} доли кадра, центр по Y = {r['subject_center_y']}",
                  "- палитра: " + ", ".join(
                      f"rgb({p['rgb'][0]},{p['rgb'][1]},{p['rgb'][2]}) {int(p['share']*100)}%"
                      for p in r["palette"]),
                  f"- контактный лист: `{os.path.relpath(r['sheet'], STUDIO)}`", ""]
    text = "\n".join(lines)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="разбор референс-роликов")
    ap.add_argument("paths", nargs="+", help="файлы или маски: studio/reference/*.mp4")
    ap.add_argument("--fps", type=float, default=6.0, help="частота выборки кадров")
    ap.add_argument("--out", default=None, help="куда писать markdown-отчёт")
    ap.add_argument("--json", default=None, help="куда сложить сырые числа")
    args = ap.parse_args(argv)

    files: list[str] = []
    for p in args.paths:
        files.extend(sorted(glob.glob(p)) or ([p] if os.path.exists(p) else []))
    if not files:
        print("нет файлов: положи референсы в studio/reference/ (.mp4/.mov/.webm)")
        return 1
    results = []
    for path in files:
        print(f"• {os.path.basename(path)} …", flush=True)
        try:
            results.append(analyze(path, fps=args.fps))
        except Exception as exc:                      # noqa: BLE001
            print(f"  ✗ {exc}")
    if not results:
        return 2
    text = report(results, args.out)
    print(text)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
