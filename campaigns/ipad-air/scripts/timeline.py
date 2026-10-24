"""Единый источник правды по таймингу ролика.

Используется и рендером видео (render.py), и генератором музыки (make_music.py),
поэтому картинка, титры и звук всегда синхронизированы.

Правки сценария: меняйте SCENES и VO_STARTS, пересоберите через build.sh.
"""

FPS = 30
W, H = 1080, 1920

# Длительность всего ролика, сек
TOTAL = 42.5

FADE = 0.55  # длительность кроссфейдов между сценами


def _rules():
    """Тизер-элементы (линии, плашки) считаются от тайминга сцены."""
    return None


# Каждая сцена: изображение, окно по времени, движение камеры, титры.
#
# motion: (zoom_from, zoom_to, pan_from, pan_to)
#   pan — смещение кадра по Y в долях свободного хода (0 = верх, 1 = низ)
# texts: список словарей
#   text, size, weight, y (доля высоты), align, kind
#   (kind: "brand" | "headline" | "sub" | "eyebrow"), t_in, dur
SCENES = [
    {
        "id": "hero",
        "image": "01_hero.jpg",
        "start": 0.0,
        "end": 5.4,
        "motion": (1.02, 1.13, 0.46, 0.40),
        "grade": "cool",
        "texts": [
            {"text": "iPad Air", "kind": "brand", "y": 0.688, "t_in": 1.05, "dur": 0.85},
            {"text": "Тоньше. Легче. Мощнее.", "kind": "sub", "y": 0.775, "t_in": 1.65},
        ],
    },
    {
        "id": "chip",
        "image": "02_chip.jpg",
        "start": 5.4,
        "end": 15.0,
        "motion": (1.04, 1.26, 0.50, 0.42),
        "grade": "warm",
        "texts": [
            {"text": "ЧИП M3", "kind": "eyebrow", "y": 0.560, "t_in": 5.95},
            {"text": "Скорость,\nкоторой хватает\nна любой замысел", "kind": "headline", "y": 0.607, "t_in": 6.35},
        ],
    },
    {
        "id": "pencil",
        "image": "03_creative.jpg",
        "start": 15.0,
        "end": 21.6,
        "motion": (1.16, 1.04, 0.42, 0.54),
        "grade": "cool",
        "texts": [
            {"text": "APPLE PENCIL PRO", "kind": "eyebrow", "y": 0.610, "t_in": 15.55},
            {"text": "Одна линия\nи идея на экране", "kind": "headline", "y": 0.652, "t_in": 15.95},
        ],
    },
    {
        "id": "life",
        "image": "04_lifestyle.jpg",
        "start": 21.6,
        "end": 29.0,
        "motion": (1.14, 1.02, 0.30, 0.36),
        "grade": "neutral",
        "texts": [
            {"text": "РАБОТАЙ · ТВОРИ · СМОТРИ", "kind": "eyebrow", "y": 0.628, "t_in": 22.15},
            {"text": "До 10 часов\nбез розетки", "kind": "headline", "y": 0.670, "t_in": 22.55},
        ],
    },
    {
        "id": "colors",
        "image": "05_colors.jpg",
        "start": 29.0,
        "end": 34.0,
        "motion": (1.03, 1.14, 0.60, 0.44),
        "grade": "neutral",
        "texts": [
            {"text": "СЕРЫЙ · ГОЛУБОЙ · СИРЕНЕВЫЙ · СИЯЮЩИЙ", "kind": "eyebrow", "y": 0.660, "t_in": 29.45, "size": 22},
            {"text": "Четыре цвета.\nОдин характер.", "kind": "headline", "y": 0.700, "t_in": 29.85},
        ],
    },
    {
        "id": "display",
        "image": "06_screen.jpg",
        "start": 34.0,
        "end": 38.2,
        "motion": (1.22, 1.04, 0.50, 0.50),
        "grade": "vivid",
        "texts": [
            {"text": "LIQUID RETINA", "kind": "eyebrow", "y": 0.580, "t_in": 34.55},
            {"text": "Каждый пиксель\nна своём месте", "kind": "headline", "y": 0.624, "t_in": 34.95},
        ],
    },
    {
        "id": "outro",
        "image": "07_outro.jpg",
        "start": 38.2,
        "end": 42.5,
        "motion": (1.14, 1.02, 0.50, 0.50),
        "grade": "cool",
        "texts": [
            {"text": "iPad Air", "kind": "brand_center", "y": 0.440, "t_in": 38.45, "dur": 0.9},
            {"text": "Твой следующий холст.", "kind": "sub_center", "y": 0.535, "t_in": 39.35},
            {"text": "Концепт-ролик · не является официальной рекламой", "kind": "legal", "y": 0.910, "t_in": 40.4},
        ],
    },
]

# Озвучка: файл -> (начало, конец) в секундах.
VO = [
    {"file": "vo_01.mp3", "start": 1.30},
    {"file": "vo_02.mp3", "start": 6.10},
    {"file": "vo_03.mp3", "start": 15.95},
    {"file": "vo_04.mp3", "start": 22.45},
    {"file": "vo_05.mp3", "start": 29.75},
    {"file": "vo_06.mp3", "start": 37.45},
]

# Акценты для саунд-дизайна
HITS = [s["start"] for s in SCENES if s["start"] > 0] + [0.0]
WHOOSHES = [(s["start"] - 0.35, s["start"] + 0.25) for s in SCENES[1:]]
RISER = (33.4, 38.2)

ACCENT = (124, 92, 255)      # фиолетовый акцент
ACCENT_2 = (47, 214, 255)    # голубой акцент
