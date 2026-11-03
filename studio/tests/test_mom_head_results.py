"""Published real head outputs/provenance; never an art acceptance score."""
from pathlib import Path
import gzip
import hashlib
import json
import struct
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


class HeadResultTests(unittest.TestCase):
    def test_actual_native_frames_and_frozen_recipes(self):
        for revision in ('r1','r2'):
            folder=ROOT/f'studio/reviews/mom-head-form-{revision}'
            report=json.loads((folder/'report.json').read_text())
            self.assertTrue(report['new_geometry_created']);self.assertFalse(report['art_approved'])
            self.assertFalse(report['user_approved']);self.assertFalse(report['production_swap_allowed'])
            self.assertFalse(report['embedded_python_executed'])
            self.assertEqual(len(report['images']),6)
            self.assertEqual(report['source_rest_signature'],report['candidate_rest_signature'])
            self.assertEqual(report['new_invalid_drivers'],[])
            for entry in report['images']:
                data=(ROOT/entry['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'])
                self.assertEqual(struct.unpack('>II',data[16:24]),(768,768))
            for name,digest in report['scripts'].items():
                self.assertEqual(hashlib.sha256((ROOT/'studio/tools'/name).read_bytes()).hexdigest(),digest)
            self.assertEqual(report['spec_sha256'],hashlib.sha256((ROOT/f'studio/authoring/mom-head-form-{revision}.json').read_bytes()).hexdigest())

    def test_new_indexed_geometry_not_diagnostic_only_or_topology_replacement(self):
        source=json.loads(gzip.decompress((ROOT/'studio/reviews/mom-form-audit/head-edit-data.json.gz').read_bytes()))['official-source']
        candidates=[]
        for revision in ('r1','r2'):
            folder=ROOT/f'studio/reviews/mom-head-form-{revision}'
            payload=(folder/'head-edit-data.json.gz').read_bytes();mesh=json.loads(gzip.decompress(payload))
            report=json.loads((folder/'report.json').read_text())
            self.assertEqual(hashlib.sha256(payload).hexdigest(),report['indexed_candidate_sha256'])
            for key in ('polygons','vertex_weights','shape_keys'):
                self.assertEqual(mesh[key],source[key])
            changed=np.asarray(mesh['basis_vertices'])
            self.assertGreater(np.linalg.norm(changed-source['basis_vertices'],axis=1).max(),.005)
            self.assertTrue(np.isfinite(changed).all());candidates.append(changed)
        self.assertGreater(np.abs(candidates[0]-candidates[1]).max(),.001)

    def test_visible_failures_not_promoted_to_acting_pass(self):
        folder=ROOT/'studio/reviews/mom-head-form-r2'
        review=json.loads((folder/'visual-review.json').read_text())
        report=json.loads((folder/'report.json').read_text())
        self.assertFalse(review['art_approved']);self.assertFalse(review['production_swap_allowed'])
        self.assertTrue(report['known_blink_visual_failure']);self.assertFalse(report['blink_visual_approved'])
        self.assertGreaterEqual(len(review['animation_visual_blockers']),2)
        for image in review['inspected_images']:
            self.assertEqual(hashlib.sha256((ROOT/image['path']).read_bytes()).hexdigest(),image['sha256'])
        registration=json.loads((folder/'image-review.json').read_text())
        self.assertEqual(len(registration['inputs']),3)
        for image in registration['inputs']:
            self.assertEqual(hashlib.sha256((ROOT/image['path']).read_bytes()).hexdigest(),image['sha256'])


if __name__=='__main__':
    unittest.main()
