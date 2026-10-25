"""Сцена как данные: несколько персонажей, камера, реплики, субтитры → кадры → mp4.

Зачем отдельный слой
--------------------
`puppet.py` рисует одного персонажа, `core_demo.py` — один заранее зашитый этюд.
Серия состоит из сцен, а сцена — это данные: кто где стоит, что делает, что
говорит, как ведёт себя камера. Поэтому сценарий серии лежит в JSON, а не в коде:

    studio/scenes/<id>.json

Что поддерживается
------------------
* несколько актёров в кадре, порядок отрисовки (z), позиция по X, масштаб;
* позы ключами по времени с плавным переходом (`ease_in_out`);
* эмоции таймлайном (`FaceTimeline`), мигание, микромимика;
* реплики: липсинк считается из текста (`F.lip_sync`), длительность — от длины;
* камера: наезд (`zoom`) и точка внимания (`focus`), эффект идёт по кадру;
* фон-пресет и субтитр;
* вывод: mp4 (H.264, yuv420p, faststart) или одиночный кадр для проверки.

Почему это часть ядра, а не «ещё один скрипт»: рендер кадра детерминирован
(`scene.still(scene, t)` при одинаковых данных даёт одинаковые байты), поэтому
сцену можно проверять тестом и сравнивать кадры до/после правок.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
SCENES = os.path.join(STUDIO, "scenes")
OUT = os.path.join(STUDIO, "out")
sys.path.insert(0, HERE)

import face as F  # noqa: E402
import kit  # noqa: E402
import library as L  # noqa: E402
import puppet  # noqa: E402
import rig as R  # noqa: E402

DEFAULTS = {
    "fps": 24,
    "size": [540, 960],
    "background": "studio",
    "caption": None,
}

LIMITS = {
    "fps": (12, 30),
    "width": (240, 1080),
    "height": (240, 1920),
    "dur": (0.2, 60.0),
    "scale": (0.3, 2.5),
}


class SceneError(Exception):
    """Сцена структурно некорректна — лучше упасть здесь, чем на 300-м кадре."""


# --------------------------------------------------------------------------- #
# чтение и проверка
# --------------------------------------------------------------------------- #


def scene_path(scene_id: str) -> str:
    return scene_id if scene_id.endswith(".json") else os.path.join(SCENES, f"{scene_id}.json")


def load_scene(path_or_id: str) -> dict:
    path = scene_path(path_or_id)
    if not os.path.exists(path):
        raise SceneError(f"нет сцены: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise SceneError(f"{path}: битый JSON — {exc}") from exc
    data.setdefault("id", os.path.splitext(os.path.basename(path))[0])
    return data


def _track(raw, what: str, t_end: float) -> list[tuple[float, str]]:
    """Трек [[t, id], ...] → [(t, id), ...] с проверкой порядка и границ."""
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise SceneError(f"{what}: ожидался непустой список [[время, id], ...]")
    out: list[tuple[float, str]] = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise SceneError(f"{what}: элемент {entry!r} — нужен [время, id]")
        t, pid = float(entry[0]), str(entry[1])
        if t < 0:
            raise SceneError(f"{what}: отрицательное время {t}")
        if out and t < out[-1][0] - 1e-9:
            raise SceneError(f"{what}: время идёт назад ({t} после {out[-1][0]})")
        out.append((t, pid))
    return out


def validate_scene(scene: dict) -> list[str]:
    """Список проблем. Пустой — сцену можно рендерить."""
    problems: list[str] = []
    fps = int(scene.get("fps", DEFAULTS["fps"]))
    size = scene.get("size") or DEFAULTS["size"]
    if not LIMITS["fps"][0] <= fps <= LIMITS["fps"][1]:
        problems.append(f"fps={fps} вне {LIMITS['fps']}")
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        problems.append("size должен быть [ширина, высота]")
        size = DEFAULTS["size"]
    w, h = int(size[0]), int(size[1])
    if not LIMITS["width"][0] <= w <= LIMITS["width"][1]:
        problems.append(f"ширина {w} вне {LIMITS['width']}")
    if not LIMITS["height"][0] <= h <= LIMITS["height"][1]:
        problems.append(f"высота {h} вне {LIMITS['height']}")

    shots = scene.get("shots")
    if not isinstance(shots, list) or not shots:
        problems.append("нет ни одного кадра (shots)")
        return problems

    for i, shot in enumerate(shots):
        where = f"shots[{i}]"
        dur = float(shot.get("dur", 0))
        if not LIMITS["dur"][0] <= dur <= LIMITS["dur"][1]:
            problems.append(f"{where}: dur={dur} вне {LIMITS['dur']}")
        actors = shot.get("actors")
        if not isinstance(actors, list) or not actors:
            problems.append(f"{where}: нет актёров")
            continue
        for j, actor in enumerate(actors):
            awhere = f"{where}.actors[{j}]"
            cid = actor.get("char")
            if not cid:
                problems.append(f"{awhere}: не указан char")
                continue
            try:
                kit.load_character(cid)
            except Exception as exc:                       # noqa: BLE001
                problems.append(f"{awhere}: персонаж '{cid}' — {exc}")
            x = float(actor.get("x", 0.5))
            if not 0.0 <= x <= 1.0:
                problems.append(f"{awhere}: x={x} вне 0..1")
            sc = float(actor.get("scale", 1.0))
            if not LIMITS["scale"][0] <= sc <= LIMITS["scale"][1]:
                problems.append(f"{awhere}: scale={sc} вне {LIMITS['scale']}")
            try:
                pose_track = _track(actor.get("pose"), f"{awhere}.pose", dur)
                for t, pid in pose_track:
                    if pid not in L.poses():
                        problems.append(f"{awhere}.pose: нет позы '{pid}'")
                    if t > dur + 1e-6:
                        problems.append(f"{awhere}.pose: ключ {t} позже конца кадра {dur}")
                expr_track = _track(actor.get("expr"), f"{awhere}.expr", dur)
                for t, eid in expr_track:
                    if eid not in L.expression_table():
                        problems.append(f"{awhere}.expr: нет эмоции '{eid}'")
                    if t > dur + 1e-6:
                        problems.append(f"{awhere}.expr: ключ {t} позже конца кадра {dur}")
            except SceneError as exc:
                problems.append(str(exc))
            try:
                timing = say_timing(actor)
                for say in timing:
                    if say["end"] > dur + 1e-6:
                        problems.append(
                            f"{awhere}.say: «{say['text'][:24]}…» не влезает в кадр "
                            f"(конец {say['end']:.2f} с при dur={dur:.2f}) — "
                            f"увеличьте cps, dur кадра или сдвиньте текст")
                spans = actor_spans(actor)
                for prev, cur in zip(spans, spans[1:]):
                    if cur.t0 < prev.t1 - 1e-9:
                        problems.append(
                            f"{awhere}.say: реплики накладываются "
                            f"({prev.t0:.2f}–{prev.t1:.2f} и {cur.t0:.2f}–{cur.t1:.2f}) — "
                            f"сдвиньте start или сократите текст")
                        break
                for sp in spans:
                    if sp.t1 > dur + 1e-6:
                        problems.append(
                            f"{awhere}.say: реплика не влезает в кадр "
                            f"(конец {sp.t1:.2f} с при dur={dur:.2f}) — "
                            f"увеличьте cps или сдвиньте start")
                        break
            except Exception as exc:                       # noqa: BLE001
                problems.append(f"{awhere}.say: {exc}")

            for say in actor.get("say", []) or []:
                if not str(say.get("text", "")).strip():
                    problems.append(f"{awhere}.say: пустой текст")
                start = float(say.get("start", 0.0))
                if not 0.0 <= start < dur:
                    problems.append(f"{awhere}.say: start={start} вне кадра 0..{dur}")
                cps = float(say.get("cps", 12.0))
                if not 4.0 <= cps <= 30.0:
                    problems.append(f"{awhere}.say: cps={cps} вне 4..30")
    total = sum(float(s.get("dur", 0)) for s in shots)
    if total > 300:
        problems.append(f"сцена длиной {total:.1f} с — это уже не шортс")
    return problems


# --------------------------------------------------------------------------- #
# время → состояние актёра
# --------------------------------------------------------------------------- #


def pose_at(painter: puppet.Painter, track: list[tuple[float, str]], t: float,
            blend: float = 0.28) -> R.Skeleton:
    """Поза на момент t: ключи + плавный переход за `blend` секунд до ключа."""
    if not track:
        return painter.build("idle")
    if t <= track[0][0] or len(track) == 1:
        return painter.build(track[0][1])

    idx = 0
    for i, (kt, _) in enumerate(track):
        if kt <= t:
            idx = i
    pid_a = track[idx][1]
    if idx + 1 >= len(track):
        return painter.build(pid_a)
    pid_b = track[idx + 1][1]
    t_b = track[idx + 1][0]
    span = min(blend, max((t_b - track[idx][0]) * 0.6, 1e-3))
    k = R.clamp((t - (t_b - span)) / span)
    k = R.ease_in_out(k)
    if k <= 0.0 or pid_a == pid_b:
        return painter.build(pid_a)

    sk = painter.build(pid_a)
    a = R.pose_data(pid_a, painter.spec.get("rig", "humanoid_v1"))["bones"]
    b = R.pose_data(pid_b, painter.spec.get("rig", "humanoid_v1"))["bones"]
    for name, bone in sk.bones.items():
        va = float(a.get(name, 0.0))
        vb = float(b.get(name, 0.0))
        bone.angle = bone.rest + math.radians(va + (vb - va) * k)
    ra = R.pose_data(pid_a, painter.spec.get("rig", "humanoid_v1")).get("root") or (0, 0)
    rb = R.pose_data(pid_b, painter.spec.get("rig", "humanoid_v1")).get("root") or (0, 0)
    sk.bones["root"].origin = (ra[0] + (rb[0] - ra[0]) * k, ra[1] + (rb[1] - ra[1]) * k)
    return sk.solve()


def face_at(actor: dict, t: float, expr_track, spans, blinks, seed: int) -> F.Face:
    blink = 1.0
    for bt in blinks:
        dt = t - bt
        if -0.06 <= dt <= 0.10:
            blink = min(blink, max(0.0, abs(dt) / 0.09))
    timeline = F.FaceTimeline.from_expressions(expr_track, ease="ease") if expr_track else None
    return F.face_at(t, timeline=timeline, spans=spans, blink=blink, micro=1.0, seed=seed)


def say_timing(actor: dict) -> list[dict]:
    """Раскладка реплик актёра: start/dur/end для каждой строки.

    Если `start` не указан, реплика ставится после предыдущей (+`gap`) — так
    нельзя случайно получить наложение, а сценарий остаётся читаемым.
    Возвращает список словарей: {"text", "start", "dur", "end", "cps"}.
    """
    out: list[dict] = []
    cursor = 0.0
    for say in actor.get("say", []) or []:
        text = str(say.get("text", ""))
        cps = float(say.get("cps", 12.0))
        gap = float(say.get("gap", 0.15))
        start = say.get("start")
        start = cursor if start is None else float(start)
        dur = say.get("dur")
        dur = float(dur) if dur is not None else max(len(text) / cps, 0.4)
        out.append({"text": text, "start": start, "dur": dur,
                    "end": start + dur, "cps": cps, "gap": gap})
        cursor = start + dur + gap
    return out


def actor_spans(actor: dict) -> list:
    """Спаны липсинка по всем репликам актёра (в общей шкале кадра)."""
    spans: list = []
    for say in say_timing(actor):
        spans.extend(F.lip_sync(say["text"], start=say["start"], duration=say["dur"],
                                chars_per_sec=say["cps"]))
    return sorted(spans, key=lambda s: s.t0)


# --------------------------------------------------------------------------- #
# кадр
# --------------------------------------------------------------------------- #


def _compose(shot: dict, scene: dict, t: float, quality: str) -> "object":
    from PIL import Image

    w, h = int(scene["size"][0]), int(scene["size"][1])
    # композит — в конечном разрешении; суперсэмплинг делает сам Painter внутри
    canvas = puppet.background(w, h, ground=float(shot.get("ground", 0.93)),
                               mode=str(scene.get("background", "studio")))

    for actor in sorted(shot["actors"], key=lambda a: float(a.get("z", 1))):
        spec = kit.load_character(actor["char"])
        scale = float(actor.get("scale", 1.0))
        opts = puppet.RenderOpts(width=w, height=h, quality=quality,
                                 ground=float(actor.get("ground", shot.get("ground", 0.93))),
                                 offset_x=float(actor.get("x", 0.5)) - 0.5,
                                 zoom=scale, alpha=True)
        painter = puppet.Painter(spec, opts)
        track = _track(actor.get("pose"), "pose", float(shot["dur"]))
        sk = pose_at(painter, track, t)
        R.apply_pose(sk, "breath", weight=0.55 + 0.35 * math.sin((t + float(actor.get("phase", 0))) * 2.1),
                     additive=True)

        spans = actor_spans(actor)
        blinks = R.blink_times(float(shot["dur"]) + 2.0, avg_interval=2.6,
                               seed=int(actor.get("seed", 5)))
        face = face_at(actor, t, _track(actor.get("expr"), "expr", float(shot["dur"])),
                       spans, blinks, seed=int(actor.get("seed", 5)))

        img = painter.frame(sk, face, face_expr=actor.get("expr_default", "neutral"),
                            background="none", set_name=actor.get("set"))
        canvas.alpha_composite(img)

    return _camera(canvas, shot.get("camera") or {}, w, h)


def _camera(canvas, camera: dict, w: int, h: int):
    from PIL import Image

    zoom = max(float(camera.get("zoom", 1.0)), 1.0)
    if zoom <= 1.0001:
        return canvas
    focus = R.clamp(float(camera.get("focus", 0.5)))
    cy = R.clamp(float(camera.get("y", 0.45)))
    cw, ch = int(w / zoom), int(h / zoom)
    cx = int(R.clamp(focus * w - cw / 2, 0, w - cw))
    y0 = int(R.clamp(cy * h - ch / 2, 0, h - ch))
    return canvas.crop((cx, y0, cx + cw, y0 + ch)).resize((w, h), Image.LANCZOS)


def _caption(canvas, text: str, w: int, h: int) -> None:
    """Субтитр-плашка снизу: автоподбор кегля, чтобы длинная фраза не вылезала."""
    from PIL import ImageDraw, ImageFont

    path = os.path.join(STUDIO, "fonts", "Nunito-700.ttf")
    size = max(14, int(h * 0.028))
    d = ImageDraw.Draw(canvas)

    def load(px: int):
        return (ImageFont.truetype(path, max(px, 8))
                if os.path.exists(path) else ImageFont.load_default())

    font = load(size)
    max_w = w * 0.90
    while d.textbbox((0, 0), text, font=font)[2] > max_w and size > 12:
        size = int(size * 0.93)
        font = load(size)

    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (w - tw) / 2
    y = h * 0.905
    pad = size * 0.45
    d.rounded_rectangle([x - pad, y - pad * 0.55, x + tw + pad, y + th + pad * 0.85],
                        radius=int(size * 0.5), fill=(20, 16, 14, 200))
    d.text((x, y), text, font=font, fill=(252, 248, 240, 255))


def still(scene: dict, t: float, quality: str = "high"):
    """Один кадр сцены (время — от начала сцены). Детерминирован."""
    fps = int(scene.get("fps", DEFAULTS["fps"]))
    acc = 0.0
    for shot in scene["shots"]:
        dur = float(shot["dur"])
        if t < acc + dur or shot is scene["shots"][-1]:
            return _finish(shot, scene, min(t - acc, dur - 1e-6), quality)
        acc += dur
    return _finish(scene["shots"][-1], scene, 0.0, quality)


def _finish(shot: dict, scene: dict, t: float, quality: str):
    img = _compose(shot, scene, t, quality)
    if shot.get("title"):
        _title(img, shot["title"], img.width, img.height)
    if shot.get("caption"):
        _caption(img, str(shot["caption"]), img.width, img.height)

    fade = float(shot.get("fade", 0.0))
    if fade > 0:
        dur = float(shot["dur"])
        k = min(t / fade, (dur - t) / fade, 1.0)
        if k < 1.0:
            img = _black(img, max(k, 0.0))
    return img.convert("RGB")


def _black(img, k: float):
    """Затемнение кадра для перехода (k=0 — чёрный, 1 — как есть)."""
    from PIL import Image

    black = Image.new("RGBA", img.size, (8, 6, 5, 255))
    return Image.blend(black, img, R.clamp(k))


def _title(img, data: dict, w: int, h: int) -> None:
    """Крупный титр: «стикер» с автоподбором размера, чтобы не вылезал за кадр."""
    from PIL import Image, ImageDraw, ImageFont

    text = str(data.get("text", ""))
    sub = str(data.get("sub", ""))
    if not text and not sub:
        return
    y = float(data.get("y", 0.10))
    size = int(h * float(data.get("size", 0.062)))
    max_w = w * float(data.get("width", 0.86))

    big_path = os.path.join(STUDIO, "fonts", "Montserrat-800.ttf")
    sub_path = os.path.join(STUDIO, "fonts", "Nunito-700.ttf")

    def load(path, px):
        return (ImageFont.truetype(path, max(int(px), 8))
                if os.path.exists(path) else ImageFont.load_default())

    # автоподбор: уменьшаем кегль, пока строка не влезет (русский длиннее латиницы)
    big = load(big_path, size)
    probe = ImageDraw.Draw(img)
    while probe.textbbox((0, 0), text, font=big)[2] > max_w and size > 12:
        size = int(size * 0.94)
        big = load(big_path, size)
    small = load(sub_path, size * 0.42)
    sub_size = size * 0.42
    while sub and probe.textbbox((0, 0), sub, font=small)[2] > max_w and sub_size > 10:
        sub_size *= 0.94
        small = load(sub_path, sub_size)

    box_t = probe.textbbox((0, 0), text, font=big)
    tw, th = box_t[2] - box_t[0], box_t[3] - box_t[1]
    box_s = probe.textbbox((0, 0), sub, font=small) if sub else (0, 0, 0, 0)
    sw, sh = box_s[2] - box_s[0], box_s[3] - box_s[1]

    pad_x, pad_y = size * 0.42, size * 0.34
    block_w = max(tw, sw) + pad_x * 2
    block_h = th + (sh + size * 0.34 if sub else 0) + pad_y * 2
    x0 = (w - block_w) / 2
    y0 = h * y
    card = Image.new("RGBA", img.size, (0, 0, 0, 0))
    dc = ImageDraw.Draw(card)
    dc.rounded_rectangle([x0, y0, x0 + block_w, y0 + block_h],
                         radius=int(size * 0.34), fill=(253, 247, 238, 238),
                         outline=(59, 42, 38, 60), width=max(1, int(size * 0.03)))
    img.alpha_composite(card)

    d = ImageDraw.Draw(img)
    d.text((x0 + (block_w - tw) / 2, y0 + pad_y), text, font=big, fill=data.get("color", "#3B2A26"))
    if sub:
        d.text((x0 + (block_w - sw) / 2, y0 + pad_y + th + size * 0.16), sub, font=small,
               fill=data.get("sub_color", "#7A6458"))


# --------------------------------------------------------------------------- #
# mp4
# --------------------------------------------------------------------------- #


def duration(scene: dict) -> float:
    """Длительность сцены в секундах (сумма кадров)."""
    return sum(float(s.get("dur", 0)) for s in scene["shots"])


def render(scene: dict, out: str | None = None, *, quality: str = "high",
           fps: int | None = None, from_t: float = 0.0, to_t: float | None = None,
           verbose: bool = True) -> str:
    problems = validate_scene(scene)
    if problems:
        raise SceneError("сцена невалидна:\n  " + "\n  ".join(problems))

    from imageio_ffmpeg import get_ffmpeg_exe

    w, h = int(scene["size"][0]), int(scene["size"][1])
    fps = int(fps or scene.get("fps", DEFAULTS["fps"]))
    total = duration(scene)
    to_t = total if to_t is None else min(to_t, total)
    from_t = max(from_t, 0.0)
    n = max(int(round((to_t - from_t) * fps)), 1)

    out = out or os.path.join(OUT, f"scene-{scene.get('id', 'scene')}.mp4")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)

    cmd = [get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps),
           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    if verbose:
        print(f"• сцена {scene.get('id')}: {n} кадров, {w}x{h}, {fps} fps "
              f"({from_t:.1f}–{to_t:.1f} с) → {out}")

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = from_t + i / fps
            proc.stdin.write(still(scene, t, quality).tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise SceneError("ffmpeg завершился с ошибкой")
    if verbose:
        print("✓", out)
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _cmd_validate(args) -> None:
    bad = 0
    paths = args.paths or sorted(
        os.path.join(SCENES, f) for f in os.listdir(SCENES) if f.endswith(".json")
    ) if os.path.isdir(SCENES) else []
    if not paths:
        print("нет сцен для проверки")
        return
    for path in paths:
        try:
            scene = load_scene(path)
            problems = validate_scene(scene)
        except SceneError as exc:
            print(f"✗ {path}: {exc}")
            bad += 1
            continue
        name = os.path.basename(path)
        if problems:
            print(f"✗ {name}: проблем {len(problems)}")
            for p in problems:
                print("   ", p)
            bad += 1
        else:
            print(f"✓ {name}: {len(scene['shots'])} кадров, {duration(scene):.1f} с")
    raise SystemExit(1 if bad else 0)


def _cmd_still(args) -> None:
    scene = load_scene(args.scene)
    problems = validate_scene(scene)
    if problems:
        raise SystemExit("сцена невалидна: " + "; ".join(problems[:3]))
    img = still(scene, args.t, quality=args.quality)
    out = args.out or os.path.join(OUT, f"scene-{scene.get('id')}-{args.t:.2f}.png")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    print("✓", out, img.size)


def _cmd_render(args) -> None:
    scene = load_scene(args.scene)
    if args.fps:
        scene["fps"] = args.fps
    if args.width:
        scene["size"] = [args.width, int(args.width * 16 / 9)]
    render(scene, args.out, quality=args.quality, from_t=args.from_t, to_t=args.to_t)


def _cmd_list(args) -> None:
    if not os.path.isdir(SCENES):
        print("папки сцен нет")
        return
    for name in sorted(os.listdir(SCENES)):
        if not name.endswith(".json"):
            continue
        try:
            scene = load_scene(os.path.join(SCENES, name))
            problems = validate_scene(scene)
            mark = "✓" if not problems else "✗"
            print(f"{mark} {name[:-5]:26s} {len(scene['shots'])} кадров · "
                  f"{duration(scene):5.1f} с · {len(problems)} проблем")
        except SceneError as exc:
            print(f"✗ {name:26s} {exc}")


def _cmd_info(args) -> None:
    scene = load_scene(args.scene)
    print(f"сцена {scene.get('id')} · {duration(scene):.2f} с · "
          f"{scene.get('fps', DEFAULTS['fps'])} fps · {scene['size'][0]}×{scene['size'][1]}")
    acc = 0.0
    for i, shot in enumerate(scene["shots"]):
        people = ", ".join(f"{a['char']}(x={a.get('x', 0.5)})" for a in shot["actors"])
        say = " / ".join(s.get("text", "") for a in shot["actors"] for s in a.get("say", []))
        title = (shot.get("title") or {}).get("text")
        print(f"  {i + 1}. {acc:5.2f}–{acc + shot['dur']:5.2f} с · {people}"
              + (f" · «{say}»" if say else "")
              + (f" · титр «{title}»" if title else ""))
        acc += float(shot["dur"])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="сцены студии: данные → кадры → mp4")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("info")
    p.add_argument("scene")
    p.set_defaults(func=_cmd_info)

    p = sub.add_parser("validate")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("still")
    p.add_argument("scene")
    p.add_argument("--t", type=float, default=0.0)
    p.add_argument("--quality", default="high", choices=["preview", "high", "final"])
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_still)

    p = sub.add_parser("render")
    p.add_argument("scene")
    p.add_argument("--out", default=None)
    p.add_argument("--quality", default="high", choices=["preview", "high", "final"])
    p.add_argument("--fps", type=int, default=None)
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--from", dest="from_t", type=float, default=0.0)
    p.add_argument("--to", dest="to_t", type=float, default=None)
    p.set_defaults(func=_cmd_render)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
