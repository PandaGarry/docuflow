"""Durable public diagnostic integrity, not likeness/anatomy/rig approval."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import struct
import unittest

ROOT=Path(__file__).resolve().parents[2]
FOLDER=ROOT/'studio/reviews/mom-form-audit'


class NativeAuditReceiptTests(unittest.TestCase):
    def test_native_matched_frames_and_hashes(self):
        report=json.loads((FOLDER/'native-v2/native-audit.json').read_text())
        self.assertFalse(report['new_design_created'])
        self.assertFalse(report['art_approved'])
        self.assertFalse(report['production_swap_allowed'])
        self.assertFalse(report['embedded_python_executed'])
        self.assertEqual(len(report['images']),6)
        for index,entry in enumerate(report['images']):
            data=(ROOT/entry['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
            self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II',data[16:24]),(768,768))
            self.assertEqual(entry['camera'],report['images'][index%3]['camera'])
        for name,digest in report['historical_a7_recipe_scripts'].items():
            self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
        self.assertEqual(report['script_sha256'],hashlib.sha256((ROOT/'studio/tools/mom_native_form_audit.py').read_bytes()).hexdigest())

    def test_indexed_neutral_data_not_a_fitted_target(self):
        payload=(FOLDER/'head-edit-data.json.gz').read_bytes()
        report=json.loads((FOLDER/'native-v2/native-audit.json').read_text())
        self.assertEqual(hashlib.sha256(payload).hexdigest(),report['geometry_file_sha256'])
        data=json.loads(gzip.decompress(payload))
        self.assertEqual(data['license'],'CC-BY-4.0')
        source,candidate=data['official-source'],data['existing-a7']
        self.assertEqual(source['polygons'],candidate['polygons'])
        self.assertEqual(source['vertex_weights'],candidate['vertex_weights'])
        self.assertEqual(source['shape_keys'],candidate['shape_keys'])
        for mesh in (source,candidate):
            self.assertEqual(len(mesh['basis_vertices']),6395)
            self.assertEqual(len(mesh['polygons']),6318)
            for key in ('basis_vertices','neutral_evaluated_vertices_without_subdivision'):
                self.assertEqual(len(mesh[key]),6395)
                self.assertTrue(all(len(p)==3 and all(math.isfinite(v) for v in p) for p in mesh[key]))
            self.assertTrue(all(len(p)>=3 and all(0<=i<6395 for i in p) for p in mesh['polygons']))

    def test_diagnostic_visibility_override_not_pose_rig_approval(self):
        report=json.loads((FOLDER/'native-v2/native-audit.json').read_text())
        self.assertEqual(report['diagnostic_version'],2)
        for check in report['checks'].values():
            self.assertIn('GEO-rain-scarf',check['diagnostic_visibility_only_driver_mutes'])
            self.assertEqual(check['rest_bone_signature'],check['source_rest_bone_signature'])
        self.assertEqual(report['checks']['official-source']['invalid_drivers'],report['checks']['existing-a7']['invalid_drivers'])
        self.assertIn('DEF-Spine3',report['checks']['official-source']['invalid_drivers'][0])
        # The first diagnostic and its inaccurate wardrobe isolation claim remain
        # preserved, not silently replaced by a supposedly flawless history.
        original=json.loads((FOLDER/'native-audit.json').read_text())
        self.assertNotEqual(original['script_sha256'],report['script_sha256'])
        self.assertTrue((FOLDER/'native-clay-audit.png').is_file())


if __name__=='__main__':
    unittest.main()
