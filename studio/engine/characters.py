"""Канон персонажей и реестр поз.

Зачем: кадры для серии генерируются десятками, и без карточки персонажа каждый
промпт пишется заново — персонаж «плывёт» между кадрами. Здесь хранится канон
(пропорции, одежда, приметы), из него собирается промпт, и здесь же лежит
список поз, которые нужны сценам.

Канон — единственный источник правды. Меняем одежду или причёску здесь, а не в
промптах по месту.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHARS = ROOT / "studio" / "2p5d"

# фон и свет одинаковы для всех кадров библиотеки
BG_HEX = "#00b140"
LIGHT = ("soft even studio lighting, key light from upper left, gentle rim light, "
         "no shadow on the background, no text, no watermark")
STYLE = ("high-end 3D cartoon render in the style of a modern animated feature, "
         "soft subsurface skin, clean shapes, polished materials")


@dataclass
class Character:
    key: str                     # имя папки: dad / mom / son
    name: str                    # подпись для людей
    age: str
    height_heads: float
    build: str
    face: str
    hair: str
    outfit: str
    palette: dict[str, str] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return CHARS / self.key

    def prompt(self, action: str, view: str = "front view") -> str:
        """Собрать промпт кадра: канон + действие + вид + стиль."""
        return (
            f"Full-body stylized 3D cartoon character: {self.build} {self.name}, "
            f"{self.age}, height about {self.height_heads:g} heads. "
            f"Face: {self.face}. Hair: {self.hair}. Outfit: {self.outfit}. "
            f"{action} {view}, entire figure visible from hair to shoes, centered, "
            f"flat chroma-key green background ({BG_HEX}), {LIGHT}. {STYLE}."
        )


DAD = Character(
    key="dad",
    name="father of the family",
    age="about 32",
    height_heads=6.0,
    build=("stocky broad-shouldered man with a full chest, a slight belly, thick "
           "neck, short thick limbs and big rounded hands"),
    face=("warm friendly attractive face, square jaw, defined cheekbones, big "
          "expressive eyes with dark brown irises, thick straight dark eyebrows, "
          "short boxed dark-brown beard and mustache trimmed along the jaw"),
    hair=("short dark-brown hair with a tapered fade at the sides and a neat "
          "textured quiff on top"),
    outfit=("light warm-gray crewneck sweatshirt with raglan sleeve seams and "
            "ribbed cuffs and hem, dark navy straight-leg jeans, dark brown "
            "leather boots"),
    palette={"sweater": "#c9c7c2", "jeans": "#2b3242", "boots": "#4a3527",
             "hair": "#3a2a1e", "skin": "#e8b89a"},
)

MOM = Character(
    key="mom",
    name="mother of the family",
    age="about 31",
    height_heads=6.3,
    build=("slim woman with a light figure, narrow shoulders, long limbs and neat "
           "hands"),
    face=("pretty friendly face, soft oval shape, big blue-green eyes, thin arched "
          "eyebrows, small nose, light natural makeup"),
    hair="long wavy light-brown hair parted in the middle, falling past the shoulders",
    outfit=("light beige knitted vest over a white long-sleeve top, dark gray "
            "skinny jeans, beige slip-on shoes"),
    palette={"vest": "#8a5a35", "top": "#f2efe9", "jeans": "#3d4149",
             "shoes": "#cbb59c", "hair": "#a97b4f", "skin": "#f0c5a8"},
)

SON = Character(
    key="son",
    name="little son of the family",
    age="about 3.5 years old",
    height_heads=3.6,
    build="small chubby toddler with a big head, short arms and legs, round belly",
    face=("cute toddler face with chubby cheeks, huge dark eyes, tiny nose and a "
          "mischievous grin"),
    hair="short dark hair almost fully hidden under the cap",
    outfit=("light mint cap with a big dark letter P on the front, brown fleece "
            "hoodie with the letters ABC on the chest and a kangaroo pocket, dark "
            "slim trousers, light sneakers"),
    palette={"cap": "#cfe8dd", "hoodie": "#6b4027", "trousers": "#2c2d31",
             "sneakers": "#d9d2c7", "skin": "#f2c6a8"},
)

CHARACTERS = {c.key: c for c in (DAD, MOM, SON)}


# --------------------------------------------------------------------------- #
# позы
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class PoseSpec:
    key: str
    action: str            # что персонаж делает (для промпта)
    group: str
    view: str = "front view"


# Каталог кадров. Имена — по схеме «<группа>-<что>», группы фиксированы:
# view | idle | gesture | walk | run | daily | emotion | viseme.
# Набор одинаков для всех персонажей: сцену нельзя собрать, если у мамы нет
# позы, которая есть у папы.
POSES: list[PoseSpec] = [
    # ---- ракурсы (склейки, повороты, «ушёл в профиль») ----
    PoseSpec("front", "standing in a neutral A-pose facing the camera, arms relaxed "
                      "at the sides", "view"),
    PoseSpec("three-quarter", "standing in a neutral A-pose turned about 35 degrees",
             "view", "three-quarter view"),
    PoseSpec("side", "standing in a neutral A-pose in pure profile facing right",
             "view", "side profile view"),
    PoseSpec("back", "standing in a neutral A-pose seen from behind", "view",
             "back view"),

    # ---- стойки: база любой сцены ----
    PoseSpec("idle", "standing relaxed, arms hanging at the sides", "idle"),
    PoseSpec("idle-shift", "standing relaxed with the weight on one leg, the other "
                           "knee slightly bent, arms loose", "idle"),
    PoseSpec("idle-hands-back", "standing with hands behind the back, chest slightly "
                                "out", "idle"),
    PoseSpec("idle-tired", "standing with slumped shoulders, head slightly down, "
                           "arms hanging heavy", "idle"),

    # ---- жесты: одна рука ----
    PoseSpec("wave", "waving with the right hand raised at shoulder height, palm "
                     "open toward the camera, friendly smile", "gesture"),
    PoseSpec("point", "pointing forward with the right index finger, arm extended at "
                      "shoulder height", "gesture"),
    PoseSpec("thumbs-up", "showing a confident thumbs-up with the right hand at chest "
                          "height, other hand relaxed", "gesture"),
    PoseSpec("thumbs-down", "showing a thumbs-down with the right hand, disappointed "
                            "face", "gesture"),
    PoseSpec("reach-out", "reaching forward with the right open palm as if offering a "
                          "handshake", "gesture"),
    PoseSpec("facepalm", "pressing the right palm to the forehead, eyes closed, "
                         "exasperated", "gesture"),
    PoseSpec("salute", "saluting with the right hand at the temple, straight posture",
             "gesture"),
    PoseSpec("count-one", "raising the right index finger as if making a point",
             "gesture"),

    # ---- жесты: обе руки ----
    PoseSpec("hands-hips", "standing with both hands on the hips, elbows out, "
                           "confident stance", "gesture"),
    PoseSpec("shrug", "shrugging with both palms turned up and shoulders raised, "
                      "confused expression", "gesture"),
    PoseSpec("cross-arms", "standing with arms crossed over the chest, stern look",
             "gesture"),
    PoseSpec("open-palms", "holding both palms open forward at chest height, "
                           "explaining something", "gesture"),
    PoseSpec("fist-up", "raising both clenched fists in triumph at shoulder height, "
                        "happy face", "gesture"),
    PoseSpec("clap", "clapping both hands together in front of the chest, cheerful",
             "gesture"),

    # ---- ходьба и бег: В ПРОФИЛЬ ----
    # Локомоция рисуется в профиль (как в «Симпсонах» и «Гриффинах») — так
    # читается шаг. Второй полуцикл НЕ генерируется: это зеркало первого,
    # движок отражает кадр и меняет направление.
    PoseSpec("walk-contact", "walking to the right, front foot planted with the heel "
                             "down, back leg stretched with the toe on the ground, "
                             "arms swinging in opposition", "walk",
             "full side profile view"),
    PoseSpec("walk-down", "walking to the right, weight dropping onto the front leg "
                          "which is bent, body at its lowest, back foot lifting, arms "
                          "swinging", "walk", "full side profile view"),
    PoseSpec("walk-passing", "walking to the right, back knee lifted and passing "
                             "under the body, supporting leg straight, arms close to "
                             "the body", "walk", "full side profile view"),
    PoseSpec("walk-up", "walking to the right, pushing up off the supporting leg, "
                        "body at its highest, front leg reaching forward, arms "
                        "swinging", "walk", "full side profile view"),

    # вторая половина цикла: та же фаза, но впереди другая нога
    PoseSpec("walk-contact-R", "walking to the right, with the OTHER leg forward: "
                               "front foot planted with the heel down, back leg "
                               "stretched with the toe on the ground, arms swinging "
                               "in opposition", "walk", "full side profile view"),
    PoseSpec("walk-down-R", "walking to the right with the other leg leading: weight "
                            "dropping onto the bent front leg, body at its lowest, "
                            "back foot lifting, arms swinging", "walk",
             "full side profile view"),
    PoseSpec("walk-passing-R", "walking to the right with the other leg leading: back "
                               "knee lifted and passing under the body, supporting "
                               "leg straight, arms close to the body", "walk",
             "full side profile view"),
    PoseSpec("walk-up-R", "walking to the right with the other leg leading: pushing "
                          "up off the supporting leg, body at its highest, front leg "
                          "reaching forward, arms swinging", "walk",
             "full side profile view"),

    PoseSpec("run-contact", "running to the right, front leg landing under the "
                            "body, back leg kicked up behind, arms bent and pumping, "
                            "leaning forward", "run", "full side profile view"),
    PoseSpec("run-passing", "running to the right, both feet off the ground "
                            "mid-stride, arms bent and pumping, leaning forward",
             "run", "full side profile view"),
    PoseSpec("run-contact-R", "running to the right with the other leg leading: front "
                              "leg landing under the body, back leg kicked up behind, "
                              "arms bent and pumping, leaning forward", "run",
             "full side profile view"),
    PoseSpec("run-passing-R", "running to the right with the other leg leading: both "
                              "feet off the ground mid-stride, arms bent and pumping, "
                              "leaning forward", "run", "full side profile view"),

    # ---- быт ----
    PoseSpec("sit", "sitting on an invisible chair, knees bent, hands on the knees",
             "daily"),
    PoseSpec("sit-lean", "sitting and leaning forward with elbows on the knees",
             "daily"),
    PoseSpec("crouch", "crouching down low on the haunches, hands on the knees",
             "daily"),
    PoseSpec("kneel", "kneeling on one knee, looking forward", "daily"),
    PoseSpec("reach-up", "reaching up high with the right hand as if taking "
                         "something from a top shelf", "daily"),
    PoseSpec("reach-forward", "bending slightly forward and reaching with both hands "
                              "as if picking something up", "daily"),
    PoseSpec("phone", "holding a phone to the ear with the right hand, looking "
                      "annoyed", "daily"),
    PoseSpec("read-phone", "looking down at a phone held in both hands", "daily"),
    PoseSpec("carry", "carrying a heavy invisible box with both hands in front of "
                      "the belly, leaning back slightly", "daily"),
    PoseSpec("eat", "holding a fork to the mouth with the right hand, content face",
             "daily"),
    PoseSpec("drink", "holding a mug to the mouth with the right hand", "daily"),
    PoseSpec("lie-down", "lying on his back on the floor, head turned to the side, "
                         "arms relaxed", "daily"),
]

POSE_BY_KEY = {p.key: p for p in POSES}

# Эмоции: только голова и плечи, тот же свет и ракурс — для мимики.
EMOTIONS = ["neutral", "happy", "laugh", "angry", "annoyed", "surprised",
            "sad", "scared", "thinking", "smirk", "confused", "tired", "wink"]

# Виземы для липсинка: русская речь укладывается в эти формы рта.
VISEMES = ["rest", "A", "E", "I", "O", "U", "M", "F", "S"]


def pose_prompt(char: "Character", key: str) -> str:
    """Промпт кадра: канон + действие (без фона и света — они в `prompt`)."""
    return char.prompt(POSE_BY_KEY[key].action, POSE_BY_KEY[key].view)


def emotion_prompt(char: "Character", emo: str) -> str:
    return char.prompt(
        f"head-and-shoulders portrait, expression: {_EMO_TEXT[emo]}, looking at "
        f"the camera, shoulders visible", "front view")


def viseme_prompt(char: "Character", v: str) -> str:
    return char.prompt(
        f"head-and-shoulders portrait, mouth shape for the sound form "
        f"{_VIS_TEXT[v]}, neutral expression, looking at the camera",
        "front view")


_EMO_TEXT = {
    "neutral": "calm neutral", "happy": "happy with a warm open smile",
    "laugh": "laughing out loud with eyes squeezed shut",
    "angry": "angry with narrowed eyes and furrowed brows",
    "annoyed": "annoyed, one eyebrow raised, lips pressed",
    "surprised": "surprised with wide eyes and raised brows, mouth open",
    "sad": "sad with dropped brows and a small frown",
    "scared": "scared with wide eyes and raised brows, tense mouth",
    "thinking": "thinking, looking aside, one brow lowered, lips pursed",
    "smirk": "smirking, one corner of the mouth raised, confident eyes",
    "confused": "confused, eyebrows uneven, mouth slightly open",
    "tired": "tired with half-closed eyes and a sighing mouth",
    "wink": "winking with one eye closed and a light smile",
}

_VIS_TEXT = {
    "rest": "closed relaxed lips", "A": "wide open mouth (ah)",
    "E": "mouth stretched sideways, teeth visible (eh)",
    "I": "mouth narrow and wide, teeth together (ee)",
    "O": "round open lips (oh)", "U": "puckered lips pushed forward (oo)",
    "M": "lips pressed together", "F": "upper teeth on the lower lip",
    "S": "teeth close together, lips slightly parted",
}


VIEW_MASTERS = {"front": "master-front-v2.png",
                "three-quarter": "master-three-quarter-v2.png",
                "side": "master-side-v2.png",
                "back": "master-back-v2.png"}


def pose_path(char: "Character", key: str) -> Path:
    """Путь кадра позы. Ракурсы берутся из мастеров — не дублируем файлы."""
    p = char.dir / "poses" / f"{key}.png"
    if p.exists():
        return p
    if key in VIEW_MASTERS:
        return char.dir / VIEW_MASTERS[key]
    return p


def emotion_path(char: "Character", emo: str) -> Path:
    return char.dir / "emotions" / f"{emo}.png"


def viseme_path(char: "Character", v: str) -> Path:
    return char.dir / "visemes" / f"{v}.png"
