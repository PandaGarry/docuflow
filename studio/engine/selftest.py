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

import json
import os
import shutil
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import face as F  # noqa: E402
import audio as A  # noqa: E402
import scene as S  # noqa: E402
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


@check("библиотеки: mirror_of разрешается в точное зеркало")
def _():
    src = R.pose_data("wave")
    mirrored = R.pose_data("wave_left")
    assert mirrored.get("mirror_of") == "wave"
    sk = R.apply_pose(R.build_humanoid(6.0), src)
    ref = sk.tip("hand.l")
    sk2 = R.apply_pose(R.build_humanoid(6.0), mirrored)
    got = sk2.tip("hand.r")
    assert abs(got[0] + ref[0]) < 1e-6 and abs(got[1] - ref[1]) < 1e-6, (got, ref)


@check("библиотеки: валидатор ловит битую позу")
def _():
    table = L.load("poses")
    table["poses"]["zz_broken"] = {"label": "сломано", "bones": {"no_such_bone": 5}}
    try:
        problems = L.validate()
    finally:
        del table["poses"]["zz_broken"]
        L.clear_cache()
    assert any("zz_broken" in p for p in problems), problems


@check("библиотеки: валидатор ловит несимметричный rest-скелет")
def _():
    rigs = L.load("rigs")
    bones = rigs["rigs"]["humanoid_v1"]["bones"]
    original = next(b for b in bones if b["name"] == "upper_arm.l")["rest"]
    next(b for b in bones if b["name"] == "upper_arm.l")["rest"] = original + 12
    try:
        problems = L.validate()
    finally:
        next(b for b in bones if b["name"] == "upper_arm.l")["rest"] = original
        L.clear_cache()
    assert any("upper_arm.l" in p and "зеркал" in p for p in problems), problems


@check("библиотеки: валидатор ловит эмоцию вне диапазона")
def _():
    expr = L.load("expressions")
    expr["expressions"]["zz_bad"] = {"label": "плохо", "face": {"smile": 5}}
    try:
        problems = L.validate()
    finally:
        del expr["expressions"]["zz_bad"]
        L.clear_cache()
    assert any("zz_bad" in p for p in problems), problems


@check("авторинг: поза сохраняется, читается и удаляется")
def _():
    entry = L.save_pose("zz_roundtrip", {"head": 7, "spine": -3}, root=[0.0, 0.1],
                        label="круговая", tags=["test"])
    assert entry["bones"]["head"] == 7
    L.clear_cache()
    assert "zz_roundtrip" in L.poses(), "поза не попала в файл"
    assert R.pose_data("zz_roundtrip")["bones"]["head"] == 7
    assert L.delete_pose("zz_roundtrip"), "не удалилась"
    L.clear_cache()
    assert "zz_roundtrip" not in L.poses()


@check("авторинг: мусор в позе отклоняется")
def _():
    for bad in (("BadId", {}), ("ok_id", {"no_such": 1}), ("ok_id", {"head": 999})):
        try:
            L.save_pose(bad[0], bad[1], write=False)
        except ValueError:
            continue
        raise AssertionError(f"приняли плохую позу: {bad}")
    try:
        L.save_pose("zz_mirror", {"head": 1}, mirror_of="wave", write=False)
    except ValueError:
        pass
    else:
        raise AssertionError("зеркальная поза приняла свои кости")


@check("авторинг: эмоция проверяется по параметрам и диапазонам")
def _():
    assert L.save_expression("zz_expr", {"smile": 0.5}, write=False)["face"]["smile"] == 0.5
    for bad in ({"nope": 0.5}, {"smile": 9}):
        try:
            L.save_expression("zz_expr", bad, write=False)
        except ValueError:
            continue
        raise AssertionError(f"приняли плохую эмоцию: {bad}")
    L.clear_cache()


@check("библиотеки: после откатов валидатор чист")
def _():
    problems = L.validate()
    assert not problems, problems[:5]


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


@check("пикл: зеркалирование точное (руки меняются местами)")
def _():
    sk = R.apply_pose(R.build_humanoid(6.0), "wave")
    xr, xl = sk.tip("hand.r"), sk.tip("hand.l")
    sk.mirror()
    nr, nl = sk.tip("hand.r"), sk.tip("hand.l")
    # после зеркала правая кисть — там, где была левая (и наоборот), с точностью float
    assert abs(nr[0] + xl[0]) < 1e-9 and abs(nr[1] - xl[1]) < 1e-9, (nr, xl)
    assert abs(nl[0] + xr[0]) < 1e-9 and abs(nl[1] - xr[1]) < 1e-9, (nl, xr)


@check("пикл: двойное зеркало = исходная поза")
def _():
    sk = R.apply_pose(R.build_humanoid(5.2), "think")
    before = {n: (b.world_angle, b.world_pos) for n, b in sk.bones.items()}
    sk.mirror().mirror()
    for name, (angle, pos) in before.items():
        assert abs(sk.bones[name].world_angle - angle) < 1e-9, name
        assert abs(sk.bones[name].world_pos[0] - pos[0]) < 1e-9, name
        assert abs(sk.bones[name].world_pos[1] - pos[1]) < 1e-9, name


@check("пикл: зеркало корпуса отражает наклон")
def _():
    sk = R.build_humanoid(6.0)
    sk.bones["spine"].angle -= 0.2            # наклон в сторону
    sk.solve()
    lean_before = sk.bones["head"].world_pos[0]
    sk.mirror()
    assert abs(sk.bones["head"].world_pos[0] + lean_before) < 1e-9, (lean_before, sk.bones["head"].world_pos)


@check("пикл: зеркальная поза словарём применяется как зеркало")
def _():
    src = R.pose_data("wave")
    sk_src = R.apply_pose(R.build_humanoid(6.0), src)
    hand_l = sk_src.tip("hand.l")
    sk = R.apply_pose(R.build_humanoid(6.0), {"mirror_of": "wave"})
    assert abs(sk.tip("hand.r")[0] + hand_l[0]) < 1e-6
    assert abs(sk.tip("hand.r")[1] - hand_l[1]) < 1e-6


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
# сцены
# --------------------------------------------------------------------------- #


@check("сцена: образец валиден и считается по времени")
def _():
    sc = S.load_scene("s01e01-shot01")
    problems = S.validate_scene(sc)
    assert not problems, problems
    assert abs(S.duration(sc) - 6.4) < 1e-6, S.duration(sc)
    img = S.still(sc, 0.0, quality="preview")
    assert img.size == tuple(sc["size"]), img.size
    assert img.mode == "RGB"


@check("сцена: кадр детерминирован")
def _():
    sc = S.load_scene("s01e01-shot01")
    a = S.still(sc, 2.4, quality="preview").tobytes()
    b = S.still(sc, 2.4, quality="preview").tobytes()
    assert a == b, "два рендера одного кадра различаются"


@check("сцена: валидатор ловит ошибки данных")
def _():
    sc = S.load_scene("s01e01-shot01")
    bad = json.loads(json.dumps(sc))
    bad["shots"][0]["actors"][0]["pose"] = [["0.0", "no_such_pose"]]
    assert any("no_such_pose" in p for p in S.validate_scene(bad))
    bad = json.loads(json.dumps(sc))
    bad["shots"][0]["actors"][0]["char"] = "no_such_char"
    assert any("no_such_char" in p for p in S.validate_scene(bad))
    bad = json.loads(json.dumps(sc))
    bad["shots"][0]["actors"][0]["x"] = 1.7
    assert any("x=" in p for p in S.validate_scene(bad))
    bad = json.loads(json.dumps(sc))
    bad["fps"] = 5
    assert any("fps" in p for p in S.validate_scene(bad))
    bad = json.loads(json.dumps(sc))
    bad["shots"] = []
    assert any("shots" in p for p in S.validate_scene(bad))


@check("сцена: поза на ключе берётся ровно, между ключами — смесь")
def _():
    spec = kit.load_character("dad")
    p_ = puppet.Painter(spec, puppet.RenderOpts(width=200, height=320, quality="preview"))
    track = [(0.0, "idle"), (1.0, "hands_on_hips")]
    at0 = S.pose_at(p_, track, 0.0)
    exact = p_.build("idle")
    assert abs(at0.tip("hand.r")[0] - exact.tip("hand.r")[0]) < 1e-9
    mid = S.pose_at(p_, track, 0.5)
    a = S.pose_at(p_, track, 0.0).tip("hand.r")[0]
    b = p_.build("hands_on_hips").tip("hand.r")[0]
    got = mid.tip("hand.r")[0]
    assert min(a, b) - 1e-6 <= got <= max(a, b) + 1e-6, (a, got, b)


@check("сцена: реплики не накладываются друг на друга")
def _():
    sc = S.load_scene("s01e01-shot01")
    for shot in sc["shots"]:
        for actor in shot["actors"]:
            spans = S.actor_spans(actor)
            for prev, cur in zip(spans, spans[1:]):
                assert cur.t0 >= prev.t1 - 1e-9, (prev, cur)
            for sp in spans:
                assert sp.t0 >= 0 and sp.t1 <= float(shot["dur"]) + 1e-6, sp


@check("сцена: промо валидно и рендерится покадрово")
def _():
    sc = S.load_scene("promo-s01")
    assert not S.validate_scene(sc), S.validate_scene(sc)
    assert 17.0 < S.duration(sc) < 20.0, S.duration(sc)
    img = S.still(sc, 16.0, quality="preview")
    assert img.size == tuple(sc["size"])


@check("звук: трек ровно нужной длины, без клиппинга, WAV читается")
def _():
    import tempfile
    import wave

    mono = A.make_bed(2.5, 112.0)
    assert abs(len(mono) / A.SR - 2.5) < 1e-6, len(mono) / A.SR
    assert float(abs(mono).max()) <= 1.0 + 1e-6
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bed.wav")
        A.write_wav(path, mono)
        with wave.open(path) as w:
            assert w.getnchannels() == 2 and w.getframerate() == A.SR
            dur = w.getnframes() / w.getframerate()
            assert abs(dur - 2.5) < 1e-3, dur


@check("арт-риг: скелет сажается по силуэту у всех персонажей")
def _():
    import kit
    import toon
    for cid in ("dad", "mom", "son"):
        rig = toon.ArtRig(kit.load_character(cid), work_height=600, ss=1)
        m = rig.measure
        # плечи, бёдра и стопы скелета совпадают с мерками арта (±3 % роста)
        tol = 0.03 * m["h"]
        for bone, key in (("upper_arm.r", "shoulder_y"), ("hips", "hip_y")):
            got = rig.to_px(*rig.sk_rest.bones[bone].world_pos)[1]
            assert abs(got - m[key]) < tol, (cid, bone, got, m[key])
        foot = rig.to_px(*rig.sk_rest.tip("foot.r"))[1]
        assert abs(foot - m["bottom"]) < tol, (cid, "foot", foot, m["bottom"])


@check("арт-риг: кадр в нужном размере, на прозрачном фоне, рисунок мастера")
def _():
    import kit
    import toon
    rig = toon.MeshRig(kit.load_character("dad"), work_height=600, ss=1,
                       grid_x=32, grid_y=48)
    img = rig.frame(rig.build("idle"), None, size=(240, 480))
    assert img.size == (240, 480) and img.mode == "RGBA"
    alpha = __import__("numpy").asarray(img)[..., 3]
    covered = float((alpha > 20).mean())
    assert 0.2 < covered < 0.9, covered          # персонаж в кадре, фон прозрачный


@check("арт-риг: rest-поза совпадает с рисунком мастера")
def _():
    """Главный инвариант: без движения арт-риг обязан отдавать сам мастер.

    Любая ошибка в скиннинге (сдвинутые веса, дыры от альфы, «осколки» цвета)
    мгновенно ломает это сравнение. Порог 4/255 — только сглаживание контура.
    """
    import numpy as np
    import kit
    import toon
    for cid in ("dad", "mom", "son"):
        rig = toon.ArtRig(kit.load_character(cid), work_height=560, ss=1)
        size = rig.work_size
        got = np.asarray(rig.frame(rig.sk_rest, None, size=size), np.float32)
        src = np.asarray(rig.art, np.float32)
        both = (got[..., 3] > 150) & (src[..., 3] > 150)
        diff = np.abs(got[..., :3] - src[..., :3]).mean(axis=2)[both]
        assert float(diff.mean()) < 4.0, (cid, "среднее расхождение", float(diff.mean()))
        assert float(np.percentile(diff, 95)) < 14.0, cid
        # и ни одного «дырявого» пикселя внутри плотного рисунка
        holes = int(((got[..., 3] < 60) & (src[..., 3] > 250)).sum())
        assert holes < 0.001 * both.sum(), (cid, "дырок", holes)


@check("арт-риг: лицо размечено в character.json и мимика попадает в лицо")
def _():
    import kit
    import toon
    for cid in ("dad", "mom", "son"):
        spec = kit.load_character(cid)
        face = (spec.get("art") or {}).get("face") or {}
        assert face.get("eye_l") and face.get("eye_r") and face.get("mouth"), cid
        rig = toon.ArtRig(spec, work_height=560, ss=1)
        L = rig.face_layout
        assert L["source"] == "config", (cid, L["source"])
        # брови выше глаз, рот ниже — иначе мимика уедет на кепку или подбородок
        assert L["brow_v"] < L["eyes_v"] < L["mouth_v"], cid
        # рамка лица не должна залезать на корпус (варп иначе тянет живот)
        m = rig.measure
        assert m["top"] - 2 <= L["cy"] - L["r"], (cid, "лицо выше макушки")
        assert L["cy"] + L["r"] <= m["hip_y"], (cid, "рамка лица залезает на корпус")


@check("арт-риг: кисть не «залипает» тёмным цветом штанов при шаге")
def _():
    """Регресс: джинсы рисовались поверх руки и оставляли на кисти осколки."""
    import numpy as np
    import kit
    import toon
    rig = toon.ArtRig(kit.load_character("dad"), work_height=560, ss=2)
    img = rig.frame(rig.build("walk"), None, size=(320, 640))
    a = np.asarray(img, np.float32)
    # область кисти: вокруг конца кости кисти в позе
    hx, hy = rig.to_px(*rig.build("walk").tip("hand.r"))
    scale = 320 / rig.work_size[0]
    cx, cy = hx * scale, hy * scale
    box = a[max(int(cy) - 22, 0):int(cy) + 22, max(int(cx) - 22, 0):int(cx) + 22]
    dark = ((box[..., 3] > 200) & (box[..., :3].max(axis=2) < 45))
    assert dark.mean() < 0.06, ("тёмных осколков на кисти", float(dark.mean()))


@check("арт-риг: открытый рот рисуется формой, а не растягивается варпом")
def _():
    """В мастере рот закрыт: тянуть из него «открытый» — значит получить смаз."""
    import numpy as np
    import kit
    import toon
    import face as F
    spec = kit.load_character("mom")
    rig = toon.ArtRig(spec, work_height=420, ss=1)
    w, h = rig.work_size
    face = spec["art"]["face"]
    mx, my = face["mouth"][0] * w, face["mouth"][1] * h
    aw = face["mouth_w"] * w * 0.5 * 0.7
    bh = face["mouth_h"] * h * 0.5 * 1.6
    yy, xx = np.mgrid[0:h, 0:w]
    inside = ((xx - mx) / aw) ** 2 + ((yy - my) / bh) ** 2 <= 1

    def mouth(expr):
        img = rig.frame(rig.build("idle"), F.Face.from_expression(expr), size=(w, h))
        return np.asarray(img.convert("RGB"), np.float32)[inside]

    closed = mouth("neutral")
    opened = mouth("laugh")
    # внутри рта становится заметно темнее (нарисовано нутро)…
    assert opened.mean() < closed.mean() - 20, (opened.mean(), closed.mean())
    # …и появляется светлый язык/зубы, которых в закрытом рту нет
    assert opened.max() > 200, opened.max()


@check("сцена: переход между позами не разворачивает персонажа")
def _():
    """Регресс: у зеркальной позы в словаре лежат углы с поворотом на 180°,
    и интерполяция «сырых» чисел кладёт персонажа набок."""
    import math
    import kit
    import puppet
    import scene
    spec = kit.load_character("dad")
    opts = puppet.RenderOpts(width=360, height=640, quality="low", ground=0.95,
                             offset_x=0.0, zoom=0.5, alpha=True)
    painter = scene._make_painter(spec, opts, "toon")
    track = [(0.0, "idle"), (0.8, "walk_2"), (1.6, "idle")]
    for t in (0.4, 0.6, 0.8, 1.1):
        sk = scene.pose_at(painter, track, t)
        tilt = math.degrees(sk.bones["root"].angle - sk.bones["root"].rest)
        assert abs(tilt) < 12.0, (t, "наклон корпуса", round(tilt, 1))


@check("3д: объём рисуется без дырок и без «шахматки»")
def _():
    """Базовый инвариант 3D-рендерера: замкнутая поверхность → сплошной силуэт."""
    import numpy as np
    import render3d as R3
    sph = R3.sphere(1.0, seg=32, rings=24)
    sph.color = np.array([0.8, 0.6, 0.5])
    cam = R3.Camera(eye=(0, 0, 4.0), target=(0, 0, 0), fov=32)
    img = R3.render([sph], (160, 160), cam, ss=1, background=None)
    a = img[..., 3]
    assert a[80, 80] == 255, "центр сферы должен быть непрозрачным"
    assert a[0, 0] == 0 and a[-1, -1] == 0, "фон должен остаться прозрачным"
    disc = ((np.mgrid[0:160, 0:160][1] - 79.5) ** 2 +
            (np.mgrid[0:160, 0:160][0] - 79.5) ** 2) < 55 ** 2
    assert int((a[disc] < 250).sum()) == 0, "внутри сферы не должно быть дырок"


@check("3д: тело собирается из пропорций и масштабируется целиком")
def _():
    import numpy as np
    import body3d as B
    import render3d as R3
    small = B.Proportions(height=1.0)
    big = B.Proportions(height=2.0)
    assert abs(small.head_h * 2 - big.head_h) < 1e-9
    parts_s = B.build_body(small, eyes=False)
    parts_b = B.build_body(big, eyes=False)
    vy_s = max(m.verts[:, 1].max() for m in parts_s)
    vy_b = max(m.verts[:, 1].max() for m in parts_b)
    # макушка масштабируется ровно с ростом (в пределах 3 %)
    assert abs(vy_b / vy_s - 2.0) < 0.06, (vy_s, vy_b)
    # ни одна деталь не вылезает выше макушки и ниже пола
    assert max(vy_s, vy_b / 2) < 1.02, "геометрия выше макушки"
    assert min(m.verts[:, 1].min() for m in parts_s) >= -0.01, "геометрия ниже пола"
    # все замкнутые тела ориентированы наружу (иначе рисуется изнанка)
    for m in parts_s:
        assert m.volume() > 0, f"{m.name}: нормали внутрь"
    # оболочка торса: одна поверхность, все вершины задействованы
    mesh = R3.loft([{"y": 0.0, "rx": 0.1, "rz": 0.08},
                    {"y": 0.2, "rx": 0.12, "rz": 0.09}], seg=16)
    assert len(np.unique(mesh.tris)) == len(mesh.verts)
    assert len(mesh.tris) > 30


@check("арт-риг: пределы позы считаются (подъём руки ловится)")
def _():
    import kit
    import toon
    rig = toon.MeshRig(kit.load_character("dad"), work_height=600, ss=1,
                       grid_x=24, grid_y=36)
    assert toon.pose_issues(rig, rig.build("idle")) == []
    issues = toon.pose_issues(rig, rig.build("celebrate"))
    assert issues and "ракурс" in issues[0]


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
