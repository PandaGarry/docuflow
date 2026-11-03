"""Regression checks for the current limited-animation pilot (stdlib unittest)."""
from pathlib import Path
import sys
import unittest

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'studio/tools'))
sys.path.insert(0, str(ROOT / 'studio/engine'))
from limited import blink_at, cut_green  # noqa: E402
from render_pilot import Pilot, PLAN, W, H, font, validate  # noqa: E402


class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pilot = Pilot()

    def test_timeline(self):
        validate()
        self.assertEqual(sum(s['end'] - s['start'] for s in PLAN['shots']), 40)
        self.assertEqual((W, H), (1920, 1080))

    def test_existing_alpha_is_preserved(self):
        source = Image.open(ROOT / 'studio/characters/son/views/front.png')
        self.assertTrue(np.array_equal(np.asarray(source), np.asarray(cut_green(source))))

    def test_key_preserves_mint_cap(self):
        actor = self.pilot.actors['son-cap']
        rgba = np.asarray(actor.original)
        self.assertEqual(int(rgba[10, 10, 3]), 0)
        self.assertEqual(int(rgba[100, 425, 3]), 255)
        self.assertGreater(int(rgba[100, 425, 1]), 120)
        self.assertGreater(actor.height, 1150)

    def test_motion_is_on_twos(self):
        actor = self.pilot.actors['son-search']
        a = np.asarray(actor.render(.001))
        b = np.asarray(actor.render(.04))
        c = np.asarray(actor.render(.10))
        self.assertTrue(np.array_equal(a, b))
        self.assertGreater(np.count_nonzero(a != c), 100)

    def test_mom_forearm_moves_without_moving_shoes(self):
        actor = self.pilot.actors['mom-hint']
        a = np.asarray(actor.render(1., arm=0))
        b = np.asarray(actor.render(1., arm=15))
        self.assertGreater(np.count_nonzero(a != b), 1000)
        self.assertTrue(np.array_equal(a[actor.pad + int(actor.h * .8):],
                                       b[actor.pad + int(actor.h * .8):]))

    def test_cap_hand_changes_but_face_does_not_duplicate(self):
        actor = self.pilot.actors['son-cap']
        a = np.asarray(actor.render(1., arm=0))
        b = np.asarray(actor.render(1., arm=15))
        p = actor.pad
        self.assertGreater(np.count_nonzero(a[p + 220:p + 480, p + 100:p + 240] !=
                                            b[p + 220:p + 480, p + 100:p + 240]), 500)
        # Fixed face/cap are to the right of the hand deformation's support.
        self.assertTrue(np.array_equal(a[p + 30:p + 480, p + 300:p + 620],
                                       b[p + 30:p + 480, p + 300:p + 620]))

    def test_blink_is_finite_and_returns_to_open(self):
        self.assertEqual(blink_at(2., 0), 0)
        self.assertEqual(blink_at(2.20, 0), 1)
        self.assertEqual(blink_at(2.5, 0), 0)
        actor = self.pilot.actors['son-search']
        self.assertGreater(np.count_nonzero(np.asarray(actor.head) != np.asarray(actor.closed_head)), 1000)

    def test_subtitles_fit_safe_area(self):
        for _, _, text in PLAN['subtitles']:
            lines = self.pilot.wrap(text, font(27, True), W * 1060 / 1280)
            self.assertLessEqual(len(lines), 2)
            for line in lines:
                self.assertLessEqual(font(27, True).getlength(line), W * 1060 / 1280)

    def test_frames_and_determinism(self):
        for t in (0, 7.3, 9.2, 21.3, 25.5, 27.8, 30., 39.99):
            im = self.pilot.frame(t)
            self.assertEqual(im.size, (W, H))
            self.assertEqual(im.mode, 'RGB')
        self.assertEqual(self.pilot.frame(25.5).tobytes(), self.pilot.frame(25.5).tobytes())
        self.assertLessEqual(self.pilot.drawing.cache_info().currsize, 18)


if __name__ == '__main__':
    unittest.main()
