"""Быстрые проверки ядра — без pytest, только стандартная библиотека.

Запуск:
    python studio/engine/selftest.py          # всё
    python studio/engine/selftest.py -v       # с подробностями

Что проверяется
---------------
* библиотеки (позы/эмоции/гардероб/причёски) — целостность ссылок;
* персонажи — схема, промпты, ключи ассетов, устаревание;
* скелет — рост в головах, позы, зеркалирование, IK, сериализация;
* лицо — эмоции, смешивание, виземы, липсинк, мигание;
* кукла — кадр рисуется, фон рисуется, одежда меняется без перегенерации;
* реестр — у каждого производного ассета есть ключ и промпт.

Зачем: ядро — это данные + математика, и его легко сломать незаметно
(например, поменять rest-угол и «уронить» все позы). Тесты ловят это за 2 с.
"""

from __future__ import annotations

import os
import shutil
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import face as F  # noqa: E402
import kit  # noqa: E402
import library as L  # noqa: E402
import puppet  # noqa: E402
import rig as R  # noqa: E402

VERBOSE = "-v" in sys.argv
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str):
    """Декоратор: зарегистрировать проверку."""
    def deco(fn):
        try:
            fn()
            RESULTS.append((name, True, ""))
            print(f"✓ {name}")
        except Exception as exc:  # noqa: BLE001 — тест должен показать любую ошибку
            detail = traceback.format_exc() if VERBOSE else f"{type(exc).__name__}: {exc}"
            RESULTS.append((name, False, detail))
            print(f"✗ {name}\n   {detail.splitlines()[-1]}")
        return fn
    return deco


# --------------------------------------------------------------------------- #
# библиотеки
# --------------------------------------------------------------------------- #


@check("библиотеки: целостность ссылок")
def _():
    problems = L.validate()
    assert not problems, "; ".join(problems)


@check("библиотеки: есть базовые позы, эмоции, вещи, причёски")
def _():
    for pid in ("idle", "wave", "point", "think", "surprise", "carry"):
        assert pid in L.poses(), f"нет позы {pid}"
    for eid in ("neutral", "joy", "anger", "sad", "surprise", "blink", "talk_a"):
        assert eid in L.expression_table(), f"нет эмоции {eid}"
    for slot in ("top", "bottom", "shoes"):
        assert L.items_for_slot(slot), f"пустой слот {slot}"
    assert len(L.hair_styles()) >= 8


@check("библиотеки: mirror_of даёт зеркальные углы")
def _():
    walk = L.pose("walk")
    mirrored = L.pose("walk_2")
    r = walk["bones"]["upper_arm.r"]
    assert mirrored["bones"]["upper_arm.l"] == -r, mirrored["bones"]


# --------------------------------------------------------------------------- #
# скелет
# --------------------------------------------------------------------------- #


@check("пикл: рост в головах соблюдается (6.5 / 4.4)")
def _():
    for target in (6.5, 5.5, 4.4):
        sk = R.build_humanoid(target)
        ratio = R.stature(sk) / R.head_diameter(sk)
        assert abs(ratio - target) < 0.02, f"{target}: получилось {ratio:.3f}"


@check("пикл: пропорции меняют силуэт, но не рост")
def _():
    adult = R.build_humanoid(6.0)
    child = R.build_humanoid(6.0, {"leg": 0.86, "arm": 0.9, "head": 1.2})
    assert R.head_diameter(child) > R.head_diameter(adult) * 1.15
    assert abs(R.stature(child) / R.head_diameter(child) - 6.0) < 0.02


@check("пикл: поза «wave» поднимает кисть выше плеча")
def _():
    sk = R.apply_pose(R.build_humanoid(6.0), "wave")
    shoulder = sk.bones["upper_arm.r"].world_pos[1]
    hand = sk.tip("hand.r")[1]
    assert hand < shoulder - 0.5, f"кисть {hand:.2f}, плечо {shoulder:.2f}"


@check("пикл: поза «point» вытягивает кисть в сторону")
def _():
    sk = R.apply_pose(R.build_humanoid(6.0), "point")
    shoulder = sk.bones["upper_arm.r"].world_pos[0]
    hand = sk.tip("hand.r")[0]
    assert hand > shoulder + 1.2, f"кисть {hand:.2f}, плечо {shoulder:.2f}"


@check("пикл: зеркалирование симметрично")
def _():
    sk = R.apply_pose(R.build_humanoid(6.0), "wave")
    xr = sk.tip("hand.r")
    sk.mirror()
    xl = sk.tip("hand.l")
    # допуск 8 %: у плеч разные rest-углы и смещения, идеальной симметрии нет
    assert abs(xr[0] + xl[0]) < 0.25 and abs(xr[1] - xl[1]) < 0.25, (xr, xl)


@check("пикл: capture → from_dict сохраняет позу")
def _():
    sk = R.apply_pose(R.build_humanoid(6.0), "think")
    data = sk.to_dict()
    sk2 = R.Skeleton.from_dict(data)
    assert abs(sk.tip("hand.r")[0] - sk2.tip("hand.r")[0]) < 1e-6


@check("пикл: IK дотягивается до цели")
def _():
    sk = R.build_humanoid(6.0)
    target = (1.6, -1.4)
    R.hand_ik(sk, "r", target)
    tip = sk.tip("hand.r")
    reach = sk.bones["upper_arm.r"].length + sk.bones["forearm.r"].length
    dist = ((tip[0] - target[0]) ** 2 + (tip[1] - target[1]) ** 2) ** 0.5
    assert dist < reach * 0.35, f"промах {dist:.2f}"


@check("пикл: look_at поворачивает голову к цели")
def _():
    sk = R.build_humanoid(6.0)
    before = sk.bones["head"].world_angle
    R.look_at(sk, (3.0, -1.0), weight=1.0, max_deg=40)
    assert abs(sk.bones["head"].world_angle - before) > 0.05


# --------------------------------------------------------------------------- #
# лицо
# --------------------------------------------------------------------------- #


@check("лицо: эмоция меняет параметры, blend работает")
def _():
    joy = F.Face.from_expression("joy")
    neutral = F.Face.neutral()
    assert joy["smile"] > 0.5 and neutral["smile"] == 0.0
    half = neutral.blend(joy, 0.5)
    assert 0.2 < half["smile"] < 0.6, half["smile"]
    assert joy.blend(neutral, 0.0).to_dict() == joy.to_dict()


@check("лицо: параметры клампятся в объявленные диапазоны")
def _():
    f = F.Face.neutral()
    f["eye_open"] = 99.0
    assert f["eye_open"] == L.expression_params()["eye_open"]["max"]


@check("лицо: визема перекрывает только рот")
def _():
    base = F.Face.from_expression("anger")
    talk = base.with_viseme("A", 1.0)
    assert talk["mouth_open"] > base["mouth_open"] + 0.3
    assert abs(talk["brow_pinch"] - base["brow_pinch"]) < 1e-6


@check("лицо: липсинк раскладывается по времени")
def _():
    spans = F.lip_sync("Привет, это тестовая реплика!", start=1.0, duration=2.5)
    assert spans, "нет визем"
    assert abs(spans[0].t0 - 1.0) < 1e-6
    assert abs(spans[-1].t1 - 3.5) < 0.15, spans[-1].t1
    assert all(b.t0 >= a.t0 for a, b in zip(spans, spans[1:]))
    v, w = F.viseme_at(spans, 1.6)
    assert v in L.visemes() and 0 <= w <= 1


@check("лицо: blink закрывает глаза, micro не выходит за диапазон")
def _():
    f = F.face_at(1.0, blink=0.0, micro=2.0)
    assert f["eye_open"] < 0.05
    g = F.face_at(2.0, timeline=F.FaceTimeline.from_expressions([(0, "joy"), (2, "anger")]),
                  blink=1.0, micro=1.0)
    assert -1.5 <= g["look_x"] <= 1.5


# --------------------------------------------------------------------------- #
# персонажи и промпты
# --------------------------------------------------------------------------- #


@check("персонажи: схема и ссылки валидны")
def _():
    problems = kit.validate_all()
    assert not problems, "; ".join(problems)


@check("промпт: содержит стиль, запреты и хромакей")
def _():
    spec = kit.load_character("dad")
    text = kit.build_prompt(spec, pose="wave", expression="joy")
    for needle in ("stylized volumetric", "chroma key green", "Exactly two arms",
                   "same face"):
        assert needle in text, needle
    assert "Do not change or add: " in text
    assert ": no " not in text
    assert "Машет" not in text, "в промпте русский текст"


@check("промпт: одежда берётся из гардероба и меняется")
def _():
    spec = kit.load_character("dad")
    home = kit.build_prompt(spec, pose="idle", expression="calm", set_name="home")
    work = kit.build_prompt(spec, pose="idle", expression="calm", set_name="work")
    assert "sweatshirt" in home and ("shirt" in work)
    assert home != work


@check("ключи ассетов: меняются от одежды и позы, стабильны без правок")
def _():
    spec = kit.load_character("mom")
    k1 = kit.asset_key(spec, pose="idle", expression="calm")
    k2 = kit.asset_key(spec, pose="idle", expression="calm")
    k3 = kit.asset_key(spec, pose="wave", expression="calm")
    k4 = kit.asset_key(spec, pose="idle", expression="calm", outfit={"top": "shirt_blue"})
    assert k1 == k2 and k1 != k3 and k1 != k4


@check("реестр: у производных есть промпт и ключ")
def _():
    reg = kit.load_registry()
    assert reg.get("characters"), "реестр пуст — запустите artgen.py registry"
    for cid, entry in reg["characters"].items():
        assert entry["derivatives"], cid
        for d in entry["derivatives"]:
            assert d.get("prompt") and d.get("key"), f"{cid}/{d['asset']}"


# --------------------------------------------------------------------------- #
# кукла
# --------------------------------------------------------------------------- #


@check("кукла: кадр рисуется и не пустой")
def _():
    import numpy as np
    spec = kit.load_character("dad")
    img = puppet.render(spec, pose="wave", expression="joy",
                        opts=puppet.RenderOpts(width=240, height=420, ss=1))
    arr = np.asarray(img, dtype=np.int16)
    assert arr.shape == (420, 240, 3)
    assert arr.std() > 8, "кадр почти одноцветный"


@check("кукла: одежда меняется без перегенерации арта")
def _():
    import numpy as np
    spec = kit.load_character("dad")
    opts = puppet.RenderOpts(width=200, height=340, ss=1)
    a = np.asarray(puppet.render(spec, pose="idle", expression="calm", opts=opts, set_name="home"))
    b = np.asarray(puppet.render(spec, pose="idle", expression="calm", opts=opts, set_name="work"))
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).mean()
    assert diff > 2.0, f"кадры почти одинаковые ({diff:.2f})"


@check("кукла: хромакей-фон ровно зелёный по краям")
def _():
    import numpy as np
    spec = kit.load_character("son")
    img = puppet.render(spec, pose="idle", expression="calm",
                        opts=puppet.RenderOpts(width=160, height=280, ss=1),
                        background="chroma")
    arr = np.asarray(img)
    corner = arr[2, 2]
    assert abs(int(corner[1]) - 177) < 12 and corner[0] < 30, corner


@check("кукла: все эмоции дают разные кадры")
def _():
    import numpy as np
    spec = kit.load_character("dad")
    opts = puppet.RenderOpts(width=180, height=180, ss=1)
    frames = {}
    for expr in ("neutral", "joy", "anger", "sad", "surprise", "cry"):
        frames[expr] = np.asarray(puppet.render(spec, pose="idle", expression=expr,
                                                opts=opts)).astype(np.int16)
    base = frames["neutral"]
    for name, arr in frames.items():
        if name == "neutral":
            continue
        assert np.abs(arr - base).mean() > 0.2, f"эмоция {name} не отличается"


# --------------------------------------------------------------------------- #
# создание персонажа
# --------------------------------------------------------------------------- #


@check("новый персонаж: создаётся, валиден и удаляется")
def _():
    tmp_id = "_selftest_new"
    tmp_dir = kit.character_dir(tmp_id)
    try:
        spec = kit.new_character(tmp_id, "Тест Тестович", template="dad", height_heads=6.0)
        loaded = kit.load_character(tmp_id)
        assert loaded["label"] == "Тест Тестович"
        assert not kit.validate_character(loaded), kit.validate_character(loaded)
        prompt = kit.build_prompt(loaded, pose="wave", expression="joy")
        assert "тест" in prompt.lower()
        img = puppet.render(loaded, pose="idle", expression="calm",
                            opts=puppet.RenderOpts(width=120, height=200, ss=1))
        assert img.size == (120, 200)
        del spec
    finally:
        if os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)


# --------------------------------------------------------------------------- #
# итог
# --------------------------------------------------------------------------- #


def main() -> int:
    failed = [r for r in RESULTS if not r[1]]
    print()
    print(f"итог: {len(RESULTS) - len(failed)} из {len(RESULTS)} проверок пройдено")
    if failed:
        print("\nпровалились:")
        for name, _ok, detail in failed:
            print(f"  ✗ {name}")
            if VERBOSE and detail:
                print("   ", detail)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
