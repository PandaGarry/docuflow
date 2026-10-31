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


POSES: list[PoseSpec] = [
    # ракурсы (нужны для склеек и поворотов)
    PoseSpec("front", "standing in a neutral A-pose facing the camera, arms relaxed "
                      "at the sides", "view", "front view"),
    PoseSpec("three-quarter", "standing in a neutral A-pose turned about 35 degrees",
             "view", "three-quarter view"),
    PoseSpec("side", "standing in a neutral A-pose in pure profile facing right",
             "view", "side profile view"),
    PoseSpec("back", "standing in a neutral A-pose seen from behind", "view",
             "back view"),

    # стойки
    PoseSpec("idle", "standing relaxed, arms hanging at the sides", "idle"),
    PoseSpec("idle-shift", "standing relaxed with the weight on one leg, the other "
                           "knee slightly bent, arms loose", "idle"),
    PoseSpec("idle-hands-back", "standing with hands behind the back, chest slightly "
                                "out", "idle"),

    # жесты
    PoseSpec("wave", "waving with the right hand raised at shoulder height, palm "
                     "open, friendly smile", "gesture"),
    PoseSpec("point", "pointing forward with the right index finger, arm extended",
             "gesture"),
    PoseSpec("thumbs-up", "showing a confident thumbs-up with the right hand, other "
                          "hand on the hip", "gesture"),
    PoseSpec("hands-hips", "standing with both hands on the hips, elbows out, "
                           "confident stance", "gesture"),
    PoseSpec("shrug", "shrugging with both palms turned up and shoulders raised, "
                      "confused expression", "gesture"),
    PoseSpec("cross-arms", "standing with arms crossed over the chest, stern look",
             "gesture"),
    PoseSpec("open-palms", "holding both palms open forward at chest height, "
                           "explaining something", "gesture"),

    # ходьба: четыре ключа цикла
    PoseSpec("walk-contact-L", "walking, left leg forward in the contact pose, arms "
                               "swinging naturally", "walk"),
    PoseSpec("walk-passing-L", "walking, left leg passing under the body, right leg "
                               "straight", "walk"),
    PoseSpec("walk-contact-R", "walking, right leg forward in the contact pose, arms "
                               "swinging naturally", "walk"),
    PoseSpec("walk-passing-R", "walking, right leg passing under the body, left leg "
                               "straight", "walk"),

    # бег
    PoseSpec("run-A", "running fast, left leg forward, arms bent and pumping",
             "run"),
    PoseSpec("run-B", "running fast, right leg forward, both feet off the ground",
             "run"),

    # бытовые
    PoseSpec("sit", "sitting on an invisible chair, knees bent, hands on the knees",
             "daily"),
    PoseSpec("crouch", "crouching down low on the haunches, hands on the knees",
             "daily"),
    PoseSpec("reach-up", "reaching up high with the right hand as if taking "
                         "something from a top shelf", "daily"),
    PoseSpec("phone", "holding a phone to the ear with the right hand, looking "
                      "annoyed", "daily"),
]

POSE_BY_KEY = {p.key: p for p in POSES}


def pose_path(char: Character, key: str) -> Path:
    """Куда кладём кадр: studio/2p5d/<char>/poses/<key>.png"""
    return char.dir / "poses" / f"{key}.png"


def prompt_for(char: Character, key: str) -> str:
    spec = POSE_BY_KEY[key]
    return char.prompt(spec.action, spec.view)
