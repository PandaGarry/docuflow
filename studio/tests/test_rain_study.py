"""Pure edit-field/acquisition contracts. Not native render or likeness tests."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import rain_study
import rain_mom_pass
import rain_mom_pass_a2


class RainStudyTests(unittest.TestCase):
    def test_field_is_finite_and_bounded(self):
        points = np.stack(np.meshgrid(np.linspace(-.8,.8,33), np.linspace(-.2,.2,9), np.linspace(0,1.8,37)),axis=-1).reshape(-1,3)
        result = rain_mom_pass.rest_field(points)
        self.assertTrue(np.isfinite(result).all())
        self.assertLess(np.linalg.norm(result-points,axis=1).max(), .035)
        np.testing.assert_array_equal(result[:,2],points[:,2])

    def test_width_is_symmetric(self):
        points = np.array([[.08,-.10,1.4],[.12,-.07,.97],[.4,0,1.23]])
        mirrored = points.copy(); mirrored[:,0] *= -1
        result = rain_mom_pass.rest_field(points)
        result[:,0] *= -1
        np.testing.assert_allclose(result,rain_mom_pass.rest_field(mirrored),atol=1e-12)

    def test_waist_and_cheeks_are_fuller(self):
        points = np.array([[.12,-.05,.97],[.08,-.09,1.405]])
        result = rain_mom_pass.rest_field(points)
        self.assertTrue(np.all(result[:,0]>points[:,0]))

    def test_nose_is_pulled_back_not_lengthened(self):
        points=np.array([[0,-.105,1.426]])
        self.assertGreater(rain_mom_pass.rest_field(points)[0,1],points[0,1])

    def test_local_jacobians_do_not_invert(self):
        for x in np.linspace(-.25,.25,7):
            for y in (-.12,0,.12):
                for z in np.linspace(.7,1.65,17):
                    p=np.array([[x,y,z]])
                    columns=[]
                    for axis in range(3):
                        delta=np.zeros((1,3));delta[0,axis]=1e-5
                        columns.append(((rain_mom_pass.rest_field(p+delta)-rain_mom_pass.rest_field(p-delta))/2e-5)[0])
                    self.assertGreater(np.linalg.det(np.stack(columns,axis=1)),.8)

    def test_color_conversion_is_linear(self):
        np.testing.assert_allclose(rain_mom_pass.linear_color('#FFFFFF'),(1,1,1,1))
        self.assertAlmostEqual(rain_mom_pass.linear_color('#808080')[0],.2158605,places=6)

    def test_actuator_solver_handles_source_blink_gain_without_overdrive(self):
        response=lambda x: min(1,max(0,-25*x))
        result=rain_mom_pass_a2.solve_control(response,.99999)
        self.assertAlmostEqual(result['input'],-.0399996,places=6)
        self.assertAlmostEqual(result['response'],.99999,places=5)

    def test_actuator_solver_finds_smile_between_coarse_samples(self):
        result=rain_mom_pass_a2.solve_control(lambda x:min(1,max(0,80*x)),.5)
        self.assertAlmostEqual(result['input'],.00625,places=6)
        self.assertAlmostEqual(result['response'],.5,places=6)

    def test_actuator_solver_reports_unattainable_target(self):
        result=rain_mom_pass_a2.solve_control(lambda x:0,.5)
        self.assertEqual(result['response'],0)
        self.assertEqual(result['input'],0)

    def test_source_hash_mismatch_stops_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'rain-v3.zip').write_bytes(b'not the official archive')
            with self.assertRaisesRegex(ValueError,'official archive changed'):
                rain_study.acquire(path)

    def test_archive_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            with zipfile.ZipFile(path/'rain-v3.zip','w') as archive:
                archive.writestr('../escape.blend','bad')
            with patch.object(rain_study,'ARCHIVE_SHA',rain_study.sha(path/'rain-v3.zip')):
                with self.assertRaisesRegex(ValueError,'unsafe archive path'):
                    rain_study.acquire(path)
            self.assertFalse((path/'escape.blend').exists())

    def test_archive_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            info=zipfile.ZipInfo('link');info.external_attr=0o120777 << 16
            with zipfile.ZipFile(path/'rain-v3.zip','w') as archive:
                archive.writestr(info,'../outside')
            with patch.object(rain_study,'ARCHIVE_SHA',rain_study.sha(path/'rain-v3.zip')):
                with self.assertRaisesRegex(ValueError,'symlink rejected'):
                    rain_study.acquire(path)


if __name__=='__main__':
    unittest.main()
