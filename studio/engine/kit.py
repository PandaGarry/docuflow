"""Ядро персонажей: схемы, гардероб, причёски, промпты, реестр, CLI.

Один персонаж — один `studio/characters/<id>/character.json`. Из него выводятся:

* промпт для генерации любого арта (поза × эмоция × комплект одежды × ракурс);
* параметры процедурной куклы (`puppet.py`);
* ключ ассета: если поменялась одежда, причёска или поза — видно, что устарело;
* проверки: неизвестная вещь, битый цвет, несуществующая поза/эмоция.

Схема character.json (v3)
-------------------------
    id, label, role, height_heads, proportions
    identity: {desc, skin, eye, jaw, eye_spread, locked[]}
    hair:     {style, facial_hair, color}
    palette:  {hair, skin, ...}
    wardrobe: {default, sets: {имя: {top, bottom, shoes, outer?, headwear?, accessory?}}}
    personality: {default_expression, catchphrase?}
    forbidden[], voice{}

Старые файлы (v2) читаются, но `validate` просит миграцию.

Команды
-------
    python studio/engine/kit.py list [chars|poses|expressions|wardrobe|hair]
    python studio/engine/kit.py show dad [--json]
    python studio/engine/kit.py prompt dad --pose wave --expr joy [--outfit street]
    python studio/engine/kit.py plan dad --poses idle,wave --exprs neutral,joy [--write]
    python studio/engine/kit.py wear dad --set street --top shirt_blue
    python studio/engine/kit.py hair dad --style buzz
    python studio/engine/kit.py new uncle --label Дядя --from dad
    python studio/engine/kit.py validate [--strict]
    python studio/engine/kit.py stale
    python studio/engine/kit.py sheet dad
    python studio/engine/kit.py migrate
"""

from __future__ import annotations

import argparse
import copy
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
CHARACTERS = os.path.join(STUDIO, "characters")
OUT = os.path.join(STUDIO, "out")
sys.path.insert(0, HERE)

import library as L  # noqa: E402

SCHEMA_VERSION = 3

STYLE_PROMPT = (
    "Modern stylized volumetric 3D cartoon style: sculpted soft forms, painterly "
    "textures, appealing caricature proportions, clean silhouette, no harsh outline"
)

QUALITY_PROMPT = (
    "Exactly two arms, two legs, one head, two eyes, five fingers per open palm, "
    "no extra limbs, no duplicate features, no floating objects"
)

BACKGROUND_PROMPT = (
    "Perfectly flat chroma key green background (#00B140), even studio lighting, "
    "no text, no watermark, no shadow on the background"
)

CAMERAS = {
    "full": "full body shot, straight-on front view, character fully in frame, feet visible",
    "three_quarter": "full body shot, three-quarter view, character fully in frame",
    "close": "close-up of head and shoulders, front view",
    "profile": "full body shot, profile view",
}

DEFAULT_SETS = ("home", "street", "pajama", "work")


# --------------------------------------------------------------------------- #
# чтение и запись
# --------------------------------------------------------------------------- #


class CharacterError(Exception):
    pass


def character_dir(char_id: str) -> str:
    return os.path.join(CHARACTERS, char_id)


def character_path(char_id: str) -> str:
    return os.path.join(character_dir(char_id), "character.json")


def list_characters() -> list[str]:
    return sorted(
        os.path.basename(os.path.dirname(p))
        for p in glob.glob(os.path.join(CHARACTERS, "*", "character.json"))
    )


def load_character(char_id: str, *, normalize: bool = True) -> dict:
    path = character_path(char_id)
    if not os.path.exists(path):
        raise CharacterError(
            f"нет персонажа '{char_id}'. Есть: {', '.join(list_characters()) or '—'}")
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    spec.setdefault("id", char_id)
    return normalize_spec(spec) if normalize else spec


def save_character(spec: dict, *, path: str | None = None) -> str:
    path = path or character_path(spec["id"])
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def normalize_spec(spec: dict) -> dict:
    """Привести к v3: подставить умолчания, разложить старый `desc` в identity."""
    s = copy.deepcopy(spec)
    s.setdefault("schema", 2)
    ident = s.setdefault("identity", {})
    if not ident.get("desc"):
        ident["desc"] = _strip_clothing(s.get("desc", ""))
    s.setdefault("height_heads", 6.5)
    s.setdefault("proportions", {"leg": 1.0, "arm": 1.0, "torso": 1.0, "head": 1.0})
    hair = s.setdefault("hair", {})
    hair.setdefault("style", "buzz")
    hair.setdefault("facial_hair", "none")
    hair.setdefault("color", (s.get("palette") or {}).get("hair_beard", "#4A332A"))
    w = s.setdefault("wardrobe", {})
    if "sets" not in w:
        w["sets"] = {}
    w.setdefault("default", next(iter(w["sets"]), None))
    s.setdefault("personality", {})
    s["personality"].setdefault("default_expression", "neutral")
    s.setdefault("forbidden", [])
    s.setdefault("rig", "humanoid_v1")
    return s


def _strip_clothing(desc: str) -> str:
    """Грубо отрезать хвост про одежду (для миграции v2 → v3)."""
    markers = [", wearing", ", in a", ", in an", ", with a", ", light-gray", ", dark jeans"]
    cut = len(desc)
    for m in markers:
        i = desc.find(m)
        if 10 < i < cut:
            cut = i
    return desc[:cut].strip(" ,.")


# --------------------------------------------------------------------------- #
# описание персонажа для промпта
# --------------------------------------------------------------------------- #


def hair_text(spec: dict, with_facial_hair: bool = True) -> str:
    hair = spec.get("hair") or {}
    parts = []
    try:
        parts.append(L.hair_style(hair.get("style", "buzz"))["prompt"])
    except KeyError:
        pass
    if with_facial_hair:
        try:
            fh = L.facial_hair(hair.get("facial_hair", "none"))
            if fh.get("prompt"):
                parts.append(fh["prompt"])
        except KeyError:
            pass
    return ", ".join(parts)


def outfit_ids(spec: dict, set_name: str | None = None,
               overrides: dict[str, str] | None = None) -> dict[str, str]:
    wardrobe = spec.get("wardrobe") or {}
    sets = wardrobe.get("sets") or {}
    name = set_name or wardrobe.get("default")
    ids = dict(sets.get(name, {})) if name else {}
    ids.update({k: v for k, v in (overrides or {}).items() if v})
    return ids


def outfit_text(spec: dict, set_name: str | None = None,
                overrides: dict[str, str] | None = None) -> str:
    """Текстовая одежда в порядке слоёв: низ, верх, верхняя, обувь, аксессуары."""
    ids = outfit_ids(spec, set_name, overrides)
    parts = []
    for slot in L.SLOT_ORDER:
        item_id = ids.get(slot)
        if not item_id:
            continue
        try:
            prompt = L.item(item_id).get("prompt")
        except KeyError:
            prompt = None
        if prompt:
            parts.append(prompt)
    return ", ".join(parts)


def identity_text(spec: dict) -> str:
    ident = spec.get("identity") or {}
    desc = ident.get("desc") or spec.get("desc", "")
    return desc.strip().rstrip(".")


def character_text(spec: dict, set_name: str | None = None,
                   overrides: dict[str, str] | None = None) -> str:
    """Полное описание внешности: тело + причёска + борода + одежда."""
    chunks = [identity_text(spec)]
    hair = hair_text(spec)
    if hair:
        chunks.append(hair)
    clothes = outfit_text(spec, set_name, overrides)
    if clothes:
        chunks.append("wearing " + clothes)
    return ", ".join(c for c in chunks if c)


def expression_text(expr_id: str) -> str:
    """Эмоция → фраза для промпта. Источник — те же параметры, что у куклы."""
    p = L.expression(expr_id)
    label = L.expression_table()[expr_id].get("label", expr_id)
    bits: list[str] = []
    brow_raise = p.get("brow_raise", 0.0)
    brow_angle = p.get("brow_angle", 0.0)
    if brow_raise > 0.55:
        bits.append("eyebrows raised high")
    elif brow_raise < -0.25:
        bits.append("eyebrows drawn down and together")
    if brow_angle > 0.4:
        bits.append("inner brow corners lifted")
    eye_open = p.get("eye_open", 1.0)
    if eye_open < 0.15:
        bits.append("eyes closed")
    elif eye_open > 1.15:
        bits.append("eyes wide open")
    if p.get("squint", 0.0) > 0.4:
        bits.append("eyes squinting")
    if p.get("lid", 0.0) > 0.4:
        bits.append("heavy eyelids")
    if p.get("tears", 0.0) > 0.3:
        bits.append("tears in the eyes")
    if p.get("sweat", 0.0) > 0.3:
        bits.append("sweat drop on the temple")
    if p.get("blush", 0.0) > 0.15:
        bits.append("slight blush on the cheeks")
    smile = p.get("smile", 0.0)
    mouth_open = p.get("mouth_open", 0.0)
    if mouth_open > 0.5:
        bits.append("mouth wide open")
    elif mouth_open > 0.12:
        bits.append("mouth slightly open")
    if smile > 0.6:
        bits.append("big happy smile")
    elif smile > 0.2:
        bits.append("warm smile")
    elif smile < -0.35:
        bits.append("corners of the mouth pulled down")
    if p.get("mouth_skew", 0.0) > 0.4:
        bits.append("one-sided lopsided smirk")
    if p.get("teeth", 0.0) > 0.35:
        bits.append("teeth visible")
    if p.get("nose_wrinkle", 0.0) > 0.3:
        bits.append("nose wrinkled")
    if not bits:
        return "calm neutral face"
    return ", ".join(bits)


def build_prompt(spec: dict, *, pose: str = "idle", expression: str = "neutral",
                 camera: str = "full", set_name: str | None = None,
                 outfit: dict[str, str] | None = None,
                 reference: bool = True) -> str:
    """Промпт для арт-генерации. Один и тот же для любого ассета."""
    try:
        pose_data = L.pose(pose)
        pose_label = pose_data.get("label", pose)
        pose_prompt = pose_data.get("prompt") or _pose_to_prompt(pose_data)
    except KeyError:
        pose_label, pose_prompt = pose, pose

    forbidden = spec.get("forbidden") or []
    forbid = ""
    if forbidden:
        clauses = []
        for rule in forbidden:
            for part in rule.split(","):
                part = part.strip().rstrip(".")
                if not part:
                    continue
                for prefix in ("no ", "не "):
                    if part.lower().startswith(prefix):
                        part = part[len(prefix):]
                        break
                clauses.append(part)
        forbid = " Do not change or add: " + "; ".join(clauses) + "."

    ref = (" Keep the character exactly as in the provided reference sheets: "
           "same face, same facial features, same hair colour, same body proportions."
           if reference else "")

    return (
        f"{STYLE_PROMPT}. Character: {character_text(spec, set_name, outfit)}."
        f"{ref} "
        f"POSE: {pose_prompt}. "
        f"EXPRESSION: {expression_text(expression)}. "
        f"CAMERA: {CAMERAS.get(camera, camera)}. "
        f"{QUALITY_PROMPT}.{forbid} {BACKGROUND_PROMPT}."
    )


def _pose_to_prompt(pose_data: dict) -> str:
    """Если у позы нет текстового описания, собрать его из углов (грубо, но честно)."""
    bones = pose_data.get("bones") or {}
    parts = []
    for arm in ("r", "l"):
        up = bones.get(f"upper_arm.{arm}", 0.0)
        if up < -60:
            parts.append(("right" if arm == "r" else "left") + " arm raised high")
        elif up < -15:
            parts.append(("right" if arm == "r" else "left") + " arm lifted forward")
    if abs(bones.get("spine", 0.0)) > 3:
        parts.append("torso leaning slightly" if bones.get("spine", 0) > 0 else "torso leaning back")
    if bones.get("head", 0.0) > 3:
        parts.append("head tilted")
    return ", ".join(parts) or "relaxed standing pose"


# --------------------------------------------------------------------------- #
# ключи ассетов и устаревание
# --------------------------------------------------------------------------- #


def spec_fingerprint(spec: dict, set_name: str | None = None) -> str:
    """Отпечаток внешности: меняется от правки identity/hair/одежды."""
    payload = {
        "identity": spec.get("identity", {}),
        "hair": spec.get("hair", {}),
        "palette": spec.get("palette", {}),
        "outfit": outfit_ids(spec, set_name),
        "proportions": spec.get("proportions", {}),
        "height_heads": spec.get("height_heads"),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def asset_key(spec: dict, *, pose: str, expression: str, camera: str = "full",
              set_name: str | None = None, outfit: dict[str, str] | None = None,
              extra: str = "") -> str:
    """Ключ ассета: по нему видно, что нужно перегенерировать после правок."""
    payload = [spec.get("id"), spec_fingerprint(spec, set_name), pose, expression,
               camera, json.dumps(outfit_ids(spec, set_name, outfit), sort_keys=True), extra]
    return hashlib.sha256("|".join(map(str, payload)).encode()).hexdigest()[:12]


def master_fingerprint(char_id: str) -> str | None:
    path = os.path.join(character_dir(char_id), "master", "turnaround.png")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# проверки
# --------------------------------------------------------------------------- #


def validate_character(spec: dict, strict: bool = True) -> list[str]:
    problems: list[str] = []
    cid = spec.get("id", "?")

    if strict and int(spec.get("schema", 2)) < SCHEMA_VERSION:
        problems.append(f"{cid}: схема v{spec.get('schema', 2)}, ожидается v{SCHEMA_VERSION} "
                        f"(запустите `kit.py migrate`)")
    if not (spec.get("identity") or {}).get("desc"):
        problems.append(f"{cid}: пустой identity.desc")
    if not 3.0 <= float(spec.get("height_heads", 0)) <= 9.0:
        problems.append(f"{cid}: height_heads вне разумных пределов (3..9)")

    for key in ("leg", "arm", "torso", "head"):
        val = float((spec.get("proportions") or {}).get(key, 1.0))
        if not 0.5 <= val <= 2.0:
            problems.append(f"{cid}: proportions.{key}={val} вне 0.5..2.0")

    hair = spec.get("hair") or {}
    try:
        L.hair_style(hair.get("style", "buzz"))
    except KeyError as exc:
        problems.append(f"{cid}: {exc}")
    try:
        L.facial_hair(hair.get("facial_hair", "none"))
    except KeyError as exc:
        problems.append(f"{cid}: {exc}")

    wardrobe = spec.get("wardrobe") or {}
    sets = wardrobe.get("sets") or {}
    if not sets:
        problems.append(f"{cid}: пустой гардероб (wardrobe.sets)")
    if wardrobe.get("default") and wardrobe["default"] not in sets:
        problems.append(f"{cid}: wardrobe.default='{wardrobe['default']}' нет в sets")
    for set_name, items in sets.items():
        for slot, item_id in items.items():
            if slot not in L.slots():
                problems.append(f"{cid}.{set_name}: неизвестный слот '{slot}'")
                continue
            try:
                item = L.item(item_id)
            except KeyError as exc:
                problems.append(f"{cid}.{set_name}.{slot}: {exc}")
                continue
            if slot not in item.get("slots", []):
                problems.append(f"{cid}.{set_name}.{slot}: '{item_id}' не для слота '{slot}'")
        for slot, meta in L.slots().items():
            if meta.get("required") and slot not in items:
                problems.append(f"{cid}.{set_name}: нет обязательного слота '{slot}'")

    expr = (spec.get("personality") or {}).get("default_expression", "neutral")
    if expr not in L.expression_table():
        problems.append(f"{cid}: default_expression '{expr}' не найдена")

    for key, color in (spec.get("palette") or {}).items():
        if isinstance(color, str) and color.startswith("#") and not L.HEX_RE.match(color):
            problems.append(f"{cid}.palette.{key}: цвет не #RRGGBB ({color})")
    return problems


def validate_all(strict: bool = True) -> list[str]:
    problems = list(L.validate())
    for cid in list_characters():
        problems.extend(validate_character(load_character(cid), strict=strict))
    return problems


# --------------------------------------------------------------------------- #
# реестр и «что устарело»
# --------------------------------------------------------------------------- #


def registry_path() -> str:
    return os.path.join(CHARACTERS, "registry.json")


def load_registry() -> dict:
    path = registry_path()
    if not os.path.exists(path):
        return {"characters": {}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def stale_assets() -> list[dict]:
    """Ассеты, чей ключ не совпадает с текущим состоянием персонажа."""
    reg = load_registry()
    out = []
    for cid, entry in (reg.get("characters") or {}).items():
        try:
            spec = load_character(cid)
        except CharacterError:
            continue
        for d in entry.get("derivatives", []):
            if d.get("status") != "ready":
                continue
            key = asset_key(spec, pose=d.get("pose", "idle"),
                            expression=d.get("expression", "neutral"),
                            camera=d.get("camera", "full"),
                            set_name=d.get("outfit_set"), extra=d.get("extra", ""))
            if d.get("key") and d["key"] != key:
                out.append({"character": cid, "asset": d["asset"], "reason": "внешность/поза изменились"})
    return out


# --------------------------------------------------------------------------- #
# создание персонажа
# --------------------------------------------------------------------------- #


def new_character(char_id: str, label: str, *, template: str | None = None,
                  role: str = "", height_heads: float | None = None,
                  hair: str | None = None, skin: str | None = None) -> dict:
    if os.path.exists(character_path(char_id)):
        raise CharacterError(f"персонаж '{char_id}' уже существует")
    base = load_character(template) if template else normalize_spec({
        "id": char_id, "label": label, "schema": SCHEMA_VERSION,
    })
    spec = copy.deepcopy(base)
    spec.update({"id": char_id, "label": label, "schema": SCHEMA_VERSION,
                 "role": role or base.get("role", "")})
    spec["identity"]["desc"] = f"a character named {label.lower()}, " + \
        base.get("identity", {}).get("desc", "friendly cartoon person")
    if height_heads:
        spec["height_heads"] = height_heads
    if hair:
        spec.setdefault("hair", {})["style"] = hair
    if skin:
        spec["identity"]["skin"] = skin
        spec.setdefault("palette", {})["skin"] = skin
    spec["forbidden"] = list(dict.fromkeys((spec.get("forbidden") or []) +
                                          ["no extra limbs or fingers", "no text on clothing unless specified"]))
    os.makedirs(os.path.join(character_dir(char_id), "master"), exist_ok=True)
    os.makedirs(os.path.join(character_dir(char_id), "pose"), exist_ok=True)
    os.makedirs(os.path.join(character_dir(char_id), "views"), exist_ok=True)
    save_character(spec)
    return spec


# --------------------------------------------------------------------------- #
# миграция v2 → v3
# --------------------------------------------------------------------------- #


def migrate_character(char_id: str, *, write: bool = True) -> tuple[dict, list[str]]:
    """Разложить старый `desc` на identity + причёску + гардероб."""
    raw = load_character(char_id, normalize=False)
    notes: list[str] = []
    if int(raw.get("schema", 2)) >= SCHEMA_VERSION:
        return raw, ["уже v3"]

    desc = raw.get("desc", "")
    spec = normalize_spec(raw)
    spec["schema"] = SCHEMA_VERSION
    spec["identity"]["desc"] = _strip_clothing(desc)

    # причёска и борода — по ключевым словам из описания
    hair_style = "buzz"
    facial = "none"
    low = desc.lower()
    if "shaved faded sides" in low or "spiky top" in low:
        hair_style = "spiky_fade"
    elif "long wavy" in low:
        hair_style = "long_wavy_bangs"
    elif "curly" in low:
        hair_style = "curly"
    elif "cap" in low:
        hair_style = "under_cap"
    if "full neat" in low and "beard" in low:
        facial = "full_beard"
    elif "stubble" in low:
        facial = "stubble"
    elif "mustache" in low:
        facial = "mustache"
    spec["hair"] = {"style": hair_style, "facial_hair": facial,
                    "color": (raw.get("palette") or {}).get("hair_beard", "#4A332A")}

    # гардероб: ищем знакомые вещи по ключевым словам
    home: dict[str, str] = {}
    guesses = [
        ("top", ["light-gray crewneck sweatshirt", "gray crewneck sweatshirt", "sweatshirt"], "hoodie_gray"),
        ("top", ["white top", "fitted white"], "top_white_fitted"),
        ("top", ["brown hoodie"], "hoodie_brown"),
        ("bottom", ["dark jeans"], "jeans_dark"),
        ("bottom", ["dark trousers", "dark pants"], "trousers_dark"),
        ("shoes", ["brown sneakers", "sneakers"], "sneakers_brown"),
        ("shoes", ["slippers"], "slippers_home"),
        ("outer", ["puffer vest", "quilted vest"], "vest_puffer_brown"),
        ("headwear", ["mint-green baseball cap", "baseball cap", "cap with"], "cap_mint"),
    ]
    for slot, needles, item_id in guesses:
        if slot in home:
            continue
        if any(n in low for n in needles):
            home[slot] = item_id
    for slot in ("top", "bottom", "shoes"):
        if slot not in home:
            notes.append(f"{slot}: не угадал вещь, подставлена базовая")

    spec["wardrobe"] = {"default": "home", "sets": {"home": home}}
    if "cap" in low:
        spec["wardrobe"]["sets"]["street"] = dict(home, headwear="cap_black")
    spec["personality"] = {"default_expression": "neutral"}
    if write:
        save_character(spec)
    return spec, notes


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print_char(cid: str) -> None:
    spec = load_character(cid)
    print(f"\n=== {spec.get('label', cid)}  ({cid}) ===")
    print(f"роль: {spec.get('role', '—')} · рост: {spec.get('height_heads')} голов")
    print(f"внешность: {identity_text(spec)}")
    print(f"причёска: {hair_text(spec)}")
    print(f"эмоция по умолчанию: {spec.get('personality', {}).get('default_expression')}")
    sets = spec.get("wardrobe", {}).get("sets", {})
    print("комплекты:")
    for name, items in sets.items():
        mark = "•" if name == spec["wardrobe"].get("default") else " "
        print(f"  {mark} {name}: " + ", ".join(f"{s}={i}" for s, i in items.items()))
    print(f"запреты: {'; '.join(spec.get('forbidden', [])) or '—'}")
    print(f"отпечаток внешности: {spec_fingerprint(spec)}")
    print(f"промпт (home, idle, neutral):\n  {build_prompt(spec)[:400]}…")


def _cmd_list(args) -> None:
    what = args.what or "chars"
    if what == "chars":
        for cid in list_characters():
            spec = load_character(cid)
            print(f"{cid:10s} {spec.get('label',''):12s} рост {spec.get('height_heads')} · "
                  f"{len(spec.get('wardrobe', {}).get('sets', {}))} компл.")
    elif what == "poses":
        for pid, p in L.poses().items():
            print(f"{pid:15s} {p.get('label',''):36s} {' '.join(p.get('tags', []))}")
    elif what == "expressions":
        for eid, e in L.expression_table().items():
            face = e.get("face", {})
            print(f"{eid:12s} {e.get('label',''):22s} {len(face)} параметров")
    elif what == "wardrobe":
        for iid, it in L.items().items():
            print(f"{iid:22s} {','.join(it.get('slots', [])):10s} {it.get('label','')}")
    elif what == "hair":
        for hid, h in L.hair_styles().items():
            print(f"{hid:18s} {h.get('label','')}")
    else:
        raise SystemExit(f"неизвестный список: {what}")


def _cmd_show(args) -> None:
    if args.json:
        print(json.dumps(load_character(args.char), ensure_ascii=False, indent=2))
    else:
        _print_char(args.char)


def _cmd_prompt(args) -> None:
    spec = load_character(args.char)
    out = {k: v for k, v in {
        "top": args.top, "bottom": args.bottom, "shoes": args.shoes, "outer": args.outer,
        "headwear": args.headwear, "accessory": args.accessory}.items() if v}
    prompt = build_prompt(spec, pose=args.pose, expression=args.expr, camera=args.camera,
                          set_name=args.set_name, outfit=out or None)
    key = asset_key(spec, pose=args.pose, expression=args.expr, camera=args.camera,
                    set_name=args.set_name, outfit=out or None)
    print(prompt)
    print(f"\n# key={key}")


def _cmd_plan(args) -> None:
    spec = load_character(args.char)
    poses = [p.strip() for p in args.poses.split(",") if p.strip()] or ["idle"]
    exprs = [e.strip() for e in args.exprs.split(",") if e.strip()] or ["neutral"]
    plan = []
    for pose_id in poses:
        for expr in exprs:
            camera = "close" if pose_id.startswith("face/") else args.camera
            plan.append({
                "asset": f"pose/{pose_id}" if not pose_id.startswith("face/") else pose_id,
                "pose": pose_id,
                "expression": expr,
                "camera": camera,
                "set": args.set_name,
                "key": asset_key(spec, pose=pose_id, expression=expr, camera=camera,
                                 set_name=args.set_name),
                "prompt": build_prompt(spec, pose=pose_id, expression=expr, camera=camera,
                                       set_name=args.set_name),
            })
    payload = {"character": args.char, "count": len(plan), "items": plan}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.print else
          f"{len(plan)} ассетов")
    if args.write:
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, "plans", f"plan-{args.char}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print("→", path)


def _cmd_wear(args) -> None:
    spec = load_character(args.char)
    sets = spec["wardrobe"].setdefault("sets", {})
    name = args.set_name or spec["wardrobe"].get("default") or "custom"
    current = dict(sets.get(name, {}))
    changed = {}
    for slot in ("top", "bottom", "shoes", "outer", "headwear", "accessory"):
        item_id = getattr(args, slot)
        if not item_id:
            continue
        if item_id == "none":
            current.pop(slot, None)
            changed[slot] = "(снято)"
            continue
        try:
            it = L.item(item_id)
        except KeyError as exc:
            raise SystemExit(str(exc))
        if slot not in it.get("slots", []):
            raise SystemExit(f"'{item_id}' не для слота '{slot}' (это для {it['slots']})")
        current[slot] = item_id
        changed[slot] = item_id
    sets[name] = current
    spec["wardrobe"].setdefault("default", name)
    save_character(spec)
    print(f"✓ {args.char}: комплект '{name}' обновлён")
    for slot, item_id in changed.items():
        print(f"   {slot:10s} → {item_id}")
    stale = stale_assets()
    mine = [s for s in stale if s["character"] == args.char]
    if mine:
        print(f"⚠️ устарели ассеты ({len(mine)}): " + ", ".join(s["asset"] for s in mine))
    print(f"новый отпечаток внешности: {spec_fingerprint(spec)}")


def _cmd_hair(args) -> None:
    spec = load_character(args.char)
    hair = spec.setdefault("hair", {})
    try:
        if args.style:
            hair["style"] = L.hair_style(args.style) and args.style
        if args.facial:
            L.facial_hair(args.facial)
            hair["facial_hair"] = args.facial
    except KeyError as exc:
        raise SystemExit(str(exc))
    if args.color:
        hair["color"] = args.color
        spec.setdefault("palette", {})["hair_beard"] = args.color
    save_character(spec)
    print(f"✓ {args.char}: причёска {hair.get('style')}, растительность {hair.get('facial_hair')}, "
          f"цвет {hair.get('color')}")
    print("⚠️ причёска меняет силуэт головы: перегенерируйте master/face и head-ассеты, "
          "затем проверьте QA")


def _cmd_new(args) -> None:
    spec = new_character(args.char, args.label, template=args.from_char,
                         role=args.role, height_heads=args.height,
                         hair=args.hair, skin=args.skin)
    print(f"✓ создан персонаж {spec['id']} в {character_dir(args.char)}")
    print("дальше: сгенерируйте master/turnaround.png и master/face.png,")
    print(f"потом: artgen.py slice/cut и kit.py sheet {args.char}")


def _cmd_validate(args) -> None:
    problems = validate_all(strict=not args.loose)
    for p in problems:
        print("✗", p)
    print("✓ всё в порядке" if not problems else f"проблем: {len(problems)}")
    raise SystemExit(1 if problems else 0)


def _cmd_stale(args) -> None:
    stale = stale_assets()
    if not stale:
        print("✓ все готовые ассеты соответствуют текущим персонажам")
        return
    for s in stale:
        print(f"⚠️ {s['character']}/{s['asset']}: {s['reason']}")


def _cmd_sheet(args) -> None:
    import puppet
    spec = load_character(args.char)
    img = puppet.contact_sheet(spec, cell=(args.cell_w, args.cell_h))
    os.makedirs(OUT, exist_ok=True)
    path = args.out or os.path.join(OUT, f"puppet-sheet-{args.char}.png")
    img.save(path)
    print("✓", path, img.size)


def _cmd_faces(args) -> None:
    import puppet
    spec = load_character(args.char)
    img = puppet.face_sheet(spec, cell=args.cell)
    os.makedirs(OUT, exist_ok=True)
    path = args.out or os.path.join(OUT, f"puppet-faces-{args.char}.png")
    img.save(path)
    print("✓", path, img.size)


def _cmd_migrate(args) -> None:
    changed = 0
    for cid in list_characters():
        spec, notes = migrate_character(cid)
        if notes and notes != ["уже v3"]:
            print(f"✓ {cid}: мигрирован" + (f" ({'; '.join(notes)})" if notes else ""))
            changed += 1
    print(f"готово, изменено: {changed}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="ядро персонажей студии")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("what", nargs="?", choices=["chars", "poses", "expressions", "wardrobe", "hair"],
                   default="chars")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("show")
    p.add_argument("char")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=_cmd_show)

    def outfit_args(p):
        for slot in ("top", "bottom", "shoes", "outer", "headwear", "accessory"):
            p.add_argument(f"--{slot}", default=None)

    p = sub.add_parser("prompt")
    p.add_argument("char")
    p.add_argument("--pose", default="idle")
    p.add_argument("--expr", default="neutral")
    p.add_argument("--camera", default="full", choices=list(CAMERAS))
    p.add_argument("--set", dest="set_name", default=None)
    outfit_args(p)
    p.set_defaults(func=_cmd_prompt)

    p = sub.add_parser("plan")
    p.add_argument("char")
    p.add_argument("--poses", default="idle")
    p.add_argument("--exprs", default="neutral")
    p.add_argument("--camera", default="full", choices=list(CAMERAS))
    p.add_argument("--set", dest="set_name", default=None)
    p.add_argument("--write", action="store_true")
    p.add_argument("--print", action="store_true")
    p.set_defaults(func=_cmd_plan)

    p = sub.add_parser("wear")
    p.add_argument("char")
    p.add_argument("--set", dest="set_name", default=None)
    outfit_args(p)
    p.set_defaults(func=_cmd_wear)

    p = sub.add_parser("hair")
    p.add_argument("char")
    p.add_argument("--style", default=None)
    p.add_argument("--facial", default=None)
    p.add_argument("--color", default=None)
    p.set_defaults(func=_cmd_hair)

    p = sub.add_parser("new")
    p.add_argument("char")
    p.add_argument("--label", required=True)
    p.add_argument("--from", dest="from_char", default=None)
    p.add_argument("--role", default="")
    p.add_argument("--height", type=float, default=None)
    p.add_argument("--hair", default=None)
    p.add_argument("--skin", default=None)
    p.set_defaults(func=_cmd_new)

    p = sub.add_parser("validate")
    p.add_argument("--loose", action="store_true")
    p.set_defaults(func=_cmd_validate)

    p = sub.add_parser("stale")
    p.set_defaults(func=_cmd_stale)

    p = sub.add_parser("sheet")
    p.add_argument("char")
    p.add_argument("--cell-w", type=int, default=300)
    p.add_argument("--cell-h", type=int, default=480)
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_sheet)

    p = sub.add_parser("faces")
    p.add_argument("char")
    p.add_argument("--cell", type=int, default=230)
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_faces)

    p = sub.add_parser("migrate")
    p.set_defaults(func=_cmd_migrate)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
