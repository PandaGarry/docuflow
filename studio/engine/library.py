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
    """Поза по id, с уже разрешённым `mirror_of`."""
    table = poses()
    if pose_id not in table:
        raise KeyError(f"нет позы '{pose_id}'; есть: {', '.join(sorted(table))}")
    p = copy.deepcopy(table[pose_id])
    if "mirror_of" in p:
        src = pose(p["mirror_of"])
        p["bones"] = mirror_bones(src.get("bones", {}))
        p.setdefault("tags", src.get("tags", []))
        p.setdefault("label", src.get("label", pose_id) + " (зеркало)")
        if "root" in src:
            p["root"] = [-src["root"][0], src["root"][1]]
    p["id"] = pose_id
    p.setdefault("bones", {})
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


def validate() -> list[str]:
    """Проверить библиотеки. Возвращает список проблем (пустой = всё хорошо)."""
    problems: list[str] = []
    try:
        pose_table, expr_table = poses(), expression_table()
        wardrobe_d, hair_d, rig_d = wardrobe(), load("hairstyles"), rigs()
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        return [f"не читается библиотека: {exc}"]

    bone_names = {b["name"] for b in rig_d["humanoid_v1"]["bones"]}

    for pid, p in pose_table.items():
        if "mirror_of" in p:
            if p["mirror_of"] not in pose_table:
                problems.append(f"poses.{pid}: mirror_of ссылается на несуществующую '{p['mirror_of']}'")
            if p["mirror_of"] == pid:
                problems.append(f"poses.{pid}: mirror_of указывает на себя")
            continue
        for bone in p.get("bones", {}):
            if bone not in bone_names:
                problems.append(f"poses.{pid}: неизвестная кость '{bone}'")
        if len(p.get("root", [0, 0])) != 2:
            problems.append(f"poses.{pid}: root должен быть [dx, dy]")

    declared = load("expressions")["params"]
    for eid, e in expr_table.items():
        for pname in e.get("face", {}):
            if pname not in declared:
                problems.append(f"expressions.{eid}: неизвестный параметр '{pname}'")
    for vid, v in load("expressions")["visemes"].items():
        if vid == "comment":
            continue
        for pname in v:
            if pname not in declared:
                problems.append(f"visemes.{vid}: неизвестный параметр '{pname}'")

    slot_names = set(wardrobe_d["slots"])
    for iid, it in wardrobe_d["items"].items():
        if not it.get("slots"):
            problems.append(f"wardrobe.{iid}: не указан слот")
        for s in it.get("slots", []):
            if s not in slot_names:
                problems.append(f"wardrobe.{iid}: неизвестный слот '{s}'")
        for key, color in (it.get("draw") or {}).items():
            if isinstance(color, str) and color.startswith("#") and not HEX_RE.match(color):
                problems.append(f"wardrobe.{iid}.draw.{key}: цвет не #RRGGBB ({color})")

    for hid, h in hair_d["styles"].items():
        if not h.get("prompt"):
            problems.append(f"hairstyles.{hid}: нет prompt")

    if not problems:
        # ссылки между библиотеками: эмоция по умолчанию у позы должна существовать
        for pid, p in pose_table.items():
            eid = p.get("expression")
            if eid and eid not in expr_table:
                problems.append(f"poses.{pid}: эмоция '{eid}' не найдена")
    return problems


if __name__ == "__main__":
    issues = validate()
    for issue in issues:
        print("✗", issue)
    print(f"{'✓ библиотеки в порядке' if not issues else f'проблем: {len(issues)}'}")
    raise SystemExit(1 if issues else 0)
