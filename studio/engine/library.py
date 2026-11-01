"""Библиотеки студии: позы, эмоции, гардероб, причёски, профили скелета.

Всё, что должно меняться без правки кода, лежит в `studio/library/*.json`.
Этот модуль — единственная точка доступа к библиотекам: он грузит их один раз,
разрешает ссылки (например, `mirror_of`) и проверяет целостность.

Зачем так
---------
Раньше поза, эмоция и одежда были зашиты в промпты и в демо-рендер. Теперь это
данные: добавить позу = дописать объект в JSON, новая вещь в гардеробе = запись
в `wardrobe.json`. Код и контент больше не связаны.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
from typing import Iterable

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
LIBRARY_DIR = os.path.join(STUDIO, "library")

_CACHE: dict[str, dict] = {}

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

SLOT_ORDER = ("bottom", "top", "outer", "shoes", "accessory", "headwear")


# --------------------------------------------------------------------------- #
# загрузка
# --------------------------------------------------------------------------- #


def load(name: str, reload: bool = False) -> dict:
    """Прочитать `library/<name>.json` (с кешем)."""
    if not reload and name in _CACHE:
        return _CACHE[name]
    path = os.path.join(LIBRARY_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"нет библиотеки: {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _CACHE[name] = data
    return data


def clear_cache() -> None:
    _CACHE.clear()


# --------------------------------------------------------------------------- #
# позы
# --------------------------------------------------------------------------- #


def poses() -> dict[str, dict]:
    return load("poses")["poses"]


def pose(pose_id: str) -> dict:
    """Поза по id. `mirror_of` НЕ разрешается здесь: точное зеркало требует
    скелета (см. `rig.pose_data`), иначе у несимметричных rest-углов ног
    получается перекос."""
    table = poses()
    if pose_id not in table:
        raise KeyError(f"нет позы '{pose_id}'; есть: {', '.join(sorted(table))}")
    p = copy.deepcopy(table[pose_id])
    p["id"] = pose_id
    p.setdefault("bones", {})
    return p


def pose_source(pose_id: str) -> str | None:
    """Если поза — зеркало, вернуть id источника (иначе None)."""
    return pose(pose_id).get("mirror_of")


def pose_entry(pose_id: str) -> dict:
    """Метаданные позы (label, tags, expression) с учётом наследования от зеркала."""
    p = pose(pose_id)
    if p.get("mirror_of"):
        src = pose(p["mirror_of"])
        p.setdefault("tags", src.get("tags", []))
        p.setdefault("label", src.get("label", p["mirror_of"]) + " ↺")
        p.setdefault("expression", src.get("expression"))
    return p


def mirror_bones(bones: dict[str, float]) -> dict[str, float]:
    """Зеркалить позу: поменять стороны и отразить углы относительно вертикали.

    Конвенция рига: 0° — вправо, 90° — вниз. Отражение вокруг вертикальной оси:
    угол → 180° − угол, и `.r` ↔ `.l`.
    """
    out: dict[str, float] = {}
    for name, angle in bones.items():
        if name.endswith(".r"):
            name = name[:-2] + ".l"
        elif name.endswith(".l"):
            name = name[:-2] + ".r"
        out[name] = -angle
    return out


def _write(name: str, data: dict) -> str:
    """Атомарно записать библиотеку: сначала .tmp-файл, потом подмена.

    Так прерванная запись не оставляет полуразвалившийся JSON (а он — источник
    правды для всего ядра).
    """
    path = os.path.join(LIBRARY_DIR, f"{name}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    clear_cache()
    return path


def save_pose(pose_id: str, bones: dict[str, float] | None = None, *,
              root: list[float] | None = None, label: str = "",
              tags: Iterable[str] = (), expression: str | None = None,
              mirror_of: str | None = None, write: bool = True) -> dict:
    """Добавить/обновить позу. Ошибки — исключением, а не тихим пропуском.

    Это точка авторинга: снять позу со скелета (`rig.capture`), сохранить сюда —
    и она сразу доступна по id и в промптах, и в рендере, без правки кода.
    """
    if not re.match(r"^[a-z][a-z0-9_]{1,40}$", pose_id):
        raise ValueError(f"id позы '{pose_id}' — только [a-z0-9_] и начинается с буквы")
    if mirror_of:
        if mirror_of not in poses():
            raise ValueError(f"mirror_of: нет позы '{mirror_of}'")
        if mirror_of == pose_id:
            raise ValueError("mirror_of не может указывать на себя")
        if bones:
            raise ValueError("зеркальная поза не задаёт свои кости: только mirror_of")

    table = load("poses")
    bones = dict(bones or {})
    for bone, angle in bones.items():
        if bone not in _bone_names():
            raise ValueError(f"неизвестная кость '{bone}'")
        if not isinstance(angle, (int, float)) or abs(float(angle)) > 360:
            raise ValueError(f"{bone}: угол должен быть числом в -360..360 (дано {angle!r})")

    entry: dict = {"label": label or pose_id.replace("_", " ")}
    if tags:
        entry["tags"] = sorted(set(tags))
    if expression:
        if expression not in expression_table():
            raise ValueError(f"нет эмоции '{expression}'")
        entry["expression"] = expression
    if mirror_of:
        entry["mirror_of"] = mirror_of
    else:
        entry["bones"] = {k: round(float(v), 2) for k, v in sorted(bones.items())}
        entry["root"] = [round(float(v), 3) for v in (root or [0.0, 0.0])]
    table["poses"][pose_id] = entry
    if write:
        _write("poses", table)
    else:
        clear_cache()
    return table["poses"][pose_id]


def delete_pose(pose_id: str) -> bool:
    table = load("poses")
    if pose_id not in table["poses"]:
        return False
    del table["poses"][pose_id]
    for pid, p in table["poses"].items():
        if p.get("mirror_of") == pose_id:
            raise ValueError(f"позу '{pose_id}' использует зеркало '{pid}'")
    _write("poses", table)
    return True


def save_expression(expr_id: str, face: dict[str, float], *, label: str = "",
                    write: bool = True) -> dict:
    """Добавить/обновить эмоцию. Параметры проверяются по `params` и их диапазонам."""
    if not re.match(r"^[a-z][a-z0-9_]{1,40}$", expr_id):
        raise ValueError(f"id эмоции '{expr_id}' — только [a-z0-9_] и начинается с буквы")
    spec = expression_params()
    clean: dict[str, float] = {}
    for name, value in face.items():
        if name not in spec:
            raise ValueError(f"неизвестный параметр '{name}'; есть: {', '.join(sorted(spec))}")
        if not isinstance(value, (int, float)):
            raise ValueError(f"{name}: нужно число (дано {value!r})")
        lo, hi = spec[name]["min"], spec[name]["max"]
        if not lo <= float(value) <= hi:
            raise ValueError(f"{name}={value} вне диапазона {lo}..{hi}")
        clean[name] = round(float(value), 3)
    table = load("expressions")
    table["expressions"][expr_id] = {"label": label or expr_id, "face": clean}
    if write:
        _write("expressions", table)
    else:
        clear_cache()
    return table["expressions"][expr_id]


def _bone_names(rig_id: str = "humanoid_v1") -> set[str]:
    return {b["name"] for b in rig_profile(rig_id)["bones"]}


def poses_by_tag(tag: str) -> list[str]:
    return [pid for pid, p in poses().items() if tag in p.get("tags", [])]


# --------------------------------------------------------------------------- #
# эмоции
# --------------------------------------------------------------------------- #


def expression_table() -> dict[str, dict]:
    return load("expressions")["expressions"]


def expression_params() -> dict[str, dict]:
    return load("expressions")["params"]


def expression(expr_id: str) -> dict[str, float]:
    table = expression_table()
    if expr_id not in table:
        raise KeyError(f"нет эмоции '{expr_id}'; есть: {', '.join(sorted(table))}")
    return dict(table[expr_id].get("face", {}))


def visemes() -> dict[str, dict]:
    return load("expressions")["visemes"]


def viseme_params(v: str) -> dict[str, float]:
    return dict(visemes().get(v, {}))


# --------------------------------------------------------------------------- #
# гардероб
# --------------------------------------------------------------------------- #


def wardrobe() -> dict:
    return load("wardrobe")


def items() -> dict[str, dict]:
    return wardrobe()["items"]


def item(item_id: str) -> dict:
    table = items()
    if item_id not in table:
        raise KeyError(f"нет вещи '{item_id}'; есть: {', '.join(sorted(table))}")
    return table[item_id]


def items_for_slot(slot: str) -> dict[str, dict]:
    return {k: v for k, v in items().items() if slot in v.get("slots", [])}


def slots() -> dict[str, dict]:
    return wardrobe()["slots"]


def layer_of(slot: str) -> int:
    return int(wardrobe()["layers"].get(slot, 5))


# --------------------------------------------------------------------------- #
# причёски
# --------------------------------------------------------------------------- #


def hair_styles() -> dict[str, dict]:
    return load("hairstyles")["styles"]


def hair_style(style_id: str) -> dict:
    table = hair_styles()
    if style_id not in table:
        raise KeyError(f"нет причёски '{style_id}'; есть: {', '.join(sorted(table))}")
    return table[style_id]


def facial_hair_table() -> dict[str, dict]:
    return load("hairstyles")["facial_hair"]


def facial_hair(kind: str) -> dict:
    table = facial_hair_table()
    if kind not in table:
        raise KeyError(f"нет растительности '{kind}'; есть: {', '.join(sorted(table))}")
    return table[kind]


# --------------------------------------------------------------------------- #
# скелеты
# --------------------------------------------------------------------------- #


def rigs() -> dict[str, dict]:
    return load("rigs")["rigs"]


def rig_profile(rig_id: str = "humanoid_v1") -> dict:
    table = rigs()
    if rig_id not in table:
        raise KeyError(f"нет профиля скелета '{rig_id}'; есть: {', '.join(sorted(table))}")
    return table[rig_id]


# --------------------------------------------------------------------------- #
# проверка целостности
# --------------------------------------------------------------------------- #


def validate(rig_id: str = "humanoid_v1") -> list[str]:
    """Полная проверка библиотек. Пустой список = всё цело.

    Проверяется не «что файл читается», а то, из-за чего ядро ломается на
    рендере: неизвестные кости и параметры, значения вне диапазонов, битые
    ссылки в зеркальных позах, несимметричный rest-скелет, отсутствующие
    обязательные поля одежды.
    """
    problems: list[str] = []
    try:
        pose_table = poses()
        expr_table = expression_table()
        params = expression_params()
        vis = visemes()
        wardrobe_d = wardrobe()
        hair_d = load("hairstyles")
        rig_d = rigs()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"не читается библиотека: {exc}"]

    if rig_id not in rig_d:
        return [f"нет профиля скелета '{rig_id}'"]

    # --- скелет ---------------------------------------------------------- #
    bones = rig_d[rig_id]["bones"]
    names: set[str] = set()
    for spec in bones:
        name = spec.get("name", "?")
        if name in names:
            problems.append(f"rigs.{rig_id}: кость '{name}' объявлена дважды")
        names.add(name)
        if not isinstance(spec.get("rest", 0.0), (int, float)):
            problems.append(f"rigs.{rig_id}.{name}: rest не число")
        if float(spec.get("length", 0.0)) < 0:
            problems.append(f"rigs.{rig_id}.{name}: отрицательная длина")
        if "origin" in spec and len(spec["origin"]) != 2:
            problems.append(f"rigs.{rig_id}.{name}: origin должен быть [x, y]")
    for spec in bones:
        parent = spec.get("parent")
        if parent is not None and parent not in names:
            problems.append(f"rigs.{rig_id}.{spec['name']}: родитель '{parent}' не найден")
        if parent == spec.get("name"):
            problems.append(f"rigs.{rig_id}.{spec['name']}: кость — родитель сама себе")

    # rest-поза обязана быть зеркально симметричной: иначе зеркало позы и
    # левая/правая стороны выглядят по-разному (это ловилось только глазами)
    try:
        import rig as R  # локально: rig сам импортирует library

        sk = R.build_humanoid(6.0, rig_id=rig_id)
        for name, b in sk.bones.items():
            if not name.endswith(".r"):
                continue
            other = sk.bones.get(name[:-2] + ".l")
            if other is None:
                problems.append(f"rigs.{rig_id}: у кости '{name}' нет пары .l")
                continue
            if abs(b.length - other.length) > 1e-6:
                problems.append(f"rigs.{rig_id}: разная длина {name}/{other.name}")
            dx = b.world_pos[0] + other.world_pos[0]
            dy = b.world_pos[1] - other.world_pos[1]
            if abs(dx) > 1e-4 or abs(dy) > 1e-4:
                problems.append(
                    f"rigs.{rig_id}: {other.name} не зеркален {name} "
                    f"(Δ=({dx:.4f}, {dy:.4f}) ед.)")
            want = math.pi - b.world_angle
            err = abs(math.atan2(math.sin(other.world_angle - want),
                                 math.cos(other.world_angle - want)))
            if err > 1e-4:
                problems.append(
                    f"rigs.{rig_id}: угол {other.name} не зеркален {name} "
                    f"(расхождение {math.degrees(err):.2f}°)")
    except Exception as exc:                       # noqa: BLE001 — диагностика, не падение
        problems.append(f"rigs.{rig_id}: не собирается скелетом ({exc})")

    # --- позы ------------------------------------------------------------ #
    for pid, p in pose_table.items():
        if not re.match(r"^[a-z][a-z0-9_]{1,40}$", pid):
            problems.append(f"poses.{pid}: id не по формату [a-z0-9_]")
        if "mirror_of" in p:
            src = p["mirror_of"]
            if src not in pose_table:
                problems.append(f"poses.{pid}: mirror_of ссылается на несуществующую '{src}'")
            if src == pid:
                problems.append(f"poses.{pid}: mirror_of указывает на себя")
            if p.get("bones"):
                problems.append(f"poses.{pid}: у зеркальной позы свои кости — они не применятся")
        for bone, angle in (p.get("bones") or {}).items():
            if bone not in names:
                problems.append(f"poses.{pid}: неизвестная кость '{bone}'")
            if not isinstance(angle, (int, float)):
                problems.append(f"poses.{pid}.{bone}: угол не число ({angle!r})")
            elif abs(float(angle)) > 360:
                problems.append(f"poses.{pid}.{bone}: угол {angle} вне -360..360")
        root = p.get("root")
        if root is not None:
            if not isinstance(root, list) or len(root) != 2 or \
                    not all(isinstance(v, (int, float)) for v in root):
                problems.append(f"poses.{pid}: root должен быть [dx, dy] числами")
        if p.get("expression") and p["expression"] not in expr_table:
            problems.append(f"poses.{pid}: эмоция '{p['expression']}' не найдена")
        if not isinstance(p.get("tags", []), list):
            problems.append(f"poses.{pid}: tags должен быть списком")

    # --- параметры лица и эмоции ----------------------------------------- #
    for name, spec in params.items():
        lo, hi = spec.get("min"), spec.get("max")
        if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
            problems.append(f"expressions.params.{name}: min/max должны быть числами")
        elif lo >= hi:
            problems.append(f"expressions.params.{name}: min >= max")

    def check_face(where: str, face: dict) -> None:
        for pname, value in (face or {}).items():
            spec = params.get(pname)
            if spec is None:
                problems.append(f"{where}: неизвестный параметр '{pname}'")
                continue
            if not isinstance(value, (int, float)):
                problems.append(f"{where}.{pname}: не число ({value!r})")
            elif not spec["min"] <= float(value) <= spec["max"]:
                problems.append(f"{where}.{pname}={value} вне {spec['min']}..{spec['max']}")

    for eid, e in expr_table.items():
        if not e.get("label"):
            problems.append(f"expressions.{eid}: нет label")
        if not e.get("face") and eid != "neutral":
            problems.append(f"expressions.{eid}: пустое лицо (face) — будет нейтральное")
        check_face(f"expressions.{eid}", e.get("face", {}))
    for vid, v in vis.items():
        if vid == "comment":
            continue
        check_face(f"visemes.{vid}", v)

    try:
        import face as FC  # локально

        for pname in FC.DEFAULTS:
            if pname not in params:
                problems.append(f"expressions.params: нет описания для '{pname}' (есть в face.py)")
            else:
                spec = params[pname]
                if not spec["min"] <= FC.DEFAULTS[pname] <= spec["max"]:
                    problems.append(f"expressions.params.{pname}: значение по умолчанию вне диапазона")
        for pname in params:
            if pname not in FC.DEFAULTS:
                problems.append(f"expressions.params: '{pname}' не используется лицом (опечатка?)")
    except Exception:                              # noqa: BLE001
        pass

    # --- гардероб и причёски --------------------------------------------- #
    slot_names = set(wardrobe_d["slots"])
    for slot, meta in wardrobe_d["slots"].items():
        if not isinstance(meta, dict) or not meta.get("label"):
            problems.append(f"wardrobe.slots.{slot}: нет label")
    for layer_slot in wardrobe_d.get("layers", {}):
        if layer_slot not in slot_names and layer_slot != "comment":
            problems.append(f"wardrobe.layers: неизвестный слот '{layer_slot}'")
    for slot in slot_names:
        if slot not in wardrobe_d.get("layers", {}):
            problems.append(f"wardrobe.layers: нет порядка отрисовки для слота '{slot}'")

    for iid, it in wardrobe_d["items"].items():
        if not it.get("slots"):
            problems.append(f"wardrobe.{iid}: не указан слот")
        if not it.get("label"):
            problems.append(f"wardrobe.{iid}: нет label")
        if not it.get("prompt"):
            problems.append(f"wardrobe.{iid}: нет prompt (попадёт в арт-промпт пустым)")
        for sl in it.get("slots", []):
            if sl not in slot_names:
                problems.append(f"wardrobe.{iid}: неизвестный слот '{sl}'")
        draw = it.get("draw") or {}
        if not draw:
            problems.append(f"wardrobe.{iid}: пустой draw (нечего рисовать)")
        for key, val in draw.items():
            if key in ("color", "shade", "sole", "accent") or (isinstance(val, str) and val.startswith("#")):
                if not (isinstance(val, str) and HEX_RE.match(val)):
                    problems.append(f"wardrobe.{iid}.draw.{key}: цвет не #RRGGBB ({val})")
            elif key in ("bulk", "volume", "width") and not isinstance(val, (int, float)):
                problems.append(f"wardrobe.{iid}.draw.{key}: ожидалось число")

    for hid, h in hair_d["styles"].items():
        if not h.get("prompt"):
            problems.append(f"hairstyles.{hid}: нет prompt")
        if not h.get("draw"):
            problems.append(f"hairstyles.{hid}: нет draw")
    for fid, f in hair_d["facial_hair"].items():
        if not f.get("prompt"):
            problems.append(f"hairstyles.facial_hair.{fid}: нет prompt")
        if not f.get("draw"):
            problems.append(f"hairstyles.facial_hair.{fid}: нет draw")

    return problems


if __name__ == "__main__":
    issues = validate()
    for issue in issues:
        print("✗", issue)
    print(f"{'✓ библиотеки в порядке' if not issues else f'проблем: {len(issues)}'}")
    raise SystemExit(1 if issues else 0)
