"""Stdlib-only tests for planning/traceability; not tests of a new 3D engine."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('production_status', ROOT / 'studio/tools/production_status.py')
PS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PS)


class ProductionStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'proof.txt').write_text('Reviewed planning artifact\n')
        task = {'id': 'TEST-01', 'title': 'Document', 'stage': 'P0', 'gate': 'G0',
                'status': 'done', 'owner': 'agent', 'requires_approval': False,
                'depends_on': [], 'deliverables': ['a document'],
                'acceptance': ['reviewed'], 'evidence': [{'kind': 'file', 'path': 'proof.txt'}]}
        second = {**deepcopy(task), 'id': 'TEST-02', 'status': 'planned',
                  'depends_on': ['TEST-01'], 'evidence': []}
        self.plan = {'schema_version': 1, 'project': 'test', 'target': 'test target',
                     'updated': '2026-11-02', 'next_task': 'TEST-02',
                     'stages': [{'id': 'P0', 'title': 'Planning'}],
                     'gates': [{'id': 'G0', 'title': 'Plan'}], 'tasks': [task, second]}

    def errors(self):
        return PS.validate_plan(self.plan, self.root)

    def assert_error(self, fragment):
        self.assertTrue(any(fragment in e for e in self.errors()), self.errors())

    def test_valid_plan(self):
        self.assertEqual(self.errors(), [])

    def test_duplicate_id(self):
        self.plan['tasks'].append(deepcopy(self.plan['tasks'][0]))
        self.assert_error('duplicate task')

    def test_dependency_cycle(self):
        self.plan['tasks'][0]['depends_on'] = ['TEST-02']
        self.assert_error('cycle')

    def test_unknown_dependency(self):
        self.plan['tasks'][1]['depends_on'] = ['NOPE-01']
        self.assert_error('unknown dependency')

    def test_done_requires_closed_dependencies(self):
        self.plan['tasks'][0]['status'] = 'planned'
        self.plan['tasks'][1]['status'] = 'done'
        self.assert_error('incomplete dependency')

    def test_in_progress_requires_closed_dependencies(self):
        self.plan['tasks'][0]['status'] = 'planned'
        self.plan['tasks'][1]['status'] = 'in_progress'
        self.assert_error('incomplete dependency')

    def test_done_needs_evidence(self):
        self.plan['tasks'][0]['evidence'] = []
        self.assert_error('done requires evidence')

    def test_missing_evidence(self):
        self.plan['tasks'][0]['evidence'][0]['path'] = 'not-created.txt'
        self.assert_error('missing evidence')

    def test_evidence_cannot_escape_repository(self):
        self.plan['tasks'][0]['evidence'][0]['path'] = '../outside.txt'
        self.assert_error('inside the repository')

    def test_absolute_evidence_is_rejected(self):
        self.plan['tasks'][0]['evidence'][0]['path'] = '/tmp/proof.txt'
        self.assert_error('inside the repository')

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            (Path(other) / 'proof.txt').write_text('external')
            (self.root / 'external').symlink_to(other, target_is_directory=True)
            self.plan['tasks'][0]['evidence'][0]['path'] = 'external/proof.txt'
            self.assert_error('escapes the repository')

    def test_blocked_needs_reason(self):
        self.plan['tasks'][1]['status'] = 'blocked'
        self.assert_error('needs a blocker')

    def test_bad_status_is_reported_not_crashed(self):
        self.plan['tasks'][1]['status'] = []
        self.assert_error('invalid status')

    def test_unknown_stage_and_gate(self):
        self.plan['tasks'][1]['stage'] = {'wrong': True}
        self.plan['tasks'][1]['gate'] = 'G99'
        self.assert_error('unknown stage')
        self.assert_error('unknown gate')

    def test_schema_and_date(self):
        self.plan['schema_version'] = True
        self.plan['updated'] = '2026-99-99'
        self.assert_error('schema_version')
        self.assert_error('ISO date')

    def test_artistic_done_needs_approval(self):
        self.plan['tasks'][0]['requires_approval'] = True
        self.assert_error('user approval')

    def approval(self, **changes):
        record = {'task_id': 'TEST-01', 'decision': 'approved', 'approver': 'user',
                  'revision': 'dad-test-r1', 'approved_at': '2026-11-02', **changes}
        (self.root / 'approval.json').write_text(json.dumps(record))
        self.plan['tasks'][0]['requires_approval'] = True
        self.plan['tasks'][0]['revision'] = 'dad-test-r1'
        self.plan['tasks'][0]['evidence'].append({'kind': 'approval', 'path': 'approval.json'})

    def test_explicit_approval_record_is_accepted(self):
        self.approval()
        self.assertEqual(self.errors(), [])

    def test_agent_cannot_mark_itself_user_approver(self):
        # The validator checks record structure; real provenance still needs review.
        self.approval(approver='agent')
        self.assert_error('invalid approval')

    def test_approval_for_wrong_revision_task_is_rejected(self):
        self.approval(task_id='TEST-02')
        self.assert_error('invalid approval')

    def test_stale_approval_does_not_accept_changed_asset(self):
        self.approval()
        self.plan['tasks'][0]['revision'] = 'dad-test-r2'
        self.assert_error('invalid approval')

    def test_duplicate_dependency(self):
        self.plan['tasks'][1]['depends_on'] = ['TEST-01', 'TEST-01']
        self.assert_error('duplicate dependency')

    def test_next_task_is_not_finished(self):
        self.plan['next_task'] = 'TEST-01'
        self.assert_error('already done')

    def test_markdown_is_deterministic_and_does_not_check_planned_tasks(self):
        result = PS.markdown(self.plan)
        self.assertEqual(result, PS.markdown(deepcopy(self.plan)))
        self.assertIn('- [x] **TEST-01', result)
        self.assertIn('- [ ] **TEST-02', result)

    def test_cli_detects_stale_checklist(self):
        path, out = self.root / 'plan.json', self.root / 'tracker.md'
        path.write_text(json.dumps(self.plan))
        # The CLI renderer is exercised independently; root-aware validation has
        # its own tests above because fixture evidence lives in a temp repository.
        with mock.patch.object(PS, 'validate_plan', return_value=[]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            args = ['--plan', str(path), 'checklist', '--out', str(out)]
            self.assertEqual(PS.main(args + ['--write']), 0)
            self.assertEqual(PS.main(args + ['--check']), 0)
            out.write_text('stale manual checkbox')
            self.assertEqual(PS.main(args + ['--check']), 1)

    def test_doctor_does_not_claim_runtime_or_gpu_test(self):
        report = PS.environment_report('2026-11-02')
        self.assertEqual(report['renderer_smoke_test'], 'not_run')
        self.assertEqual(report['gpu'], 'not_probed')
        self.assertNotIn('credentials', report)

    def test_doctor_strict_renderer_has_nonzero_exit_if_absent(self):
        with mock.patch.object(PS.shutil, 'which', return_value=None), redirect_stdout(io.StringIO()):
            self.assertEqual(PS.main(['doctor', '--record-date', '2026-11-02', '--require-renderer']), 2)

    def test_active_documentation_links_exist(self):
        from urllib.parse import unquote, urlsplit
        import re
        paths = [ROOT / 'docs' / name for name in (
            'README.md', '33-PRODUCTION-PLAN.md', '34-ENGINE-ARCHITECTURE.md',
            '35-QUALITY-GATES.md', '36-PRODUCTION-TRACKER.md', '37-DECISION-LOG.md',
            '38-BLENDER-MVP.md', '39-EXTERNAL-PACKAGES-AND-BOUNDED-WORKERS.md')]
        for path in paths:
            for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', path.read_text()):
                link = urlsplit(target)
                if link.scheme or not link.path:
                    continue
                destination = (path.parent / unquote(link.path)).resolve()
                self.assertTrue(destination.is_file(), f'{path.name}: missing {target}')

    def test_live_repository_plan_validates(self):
        plan = json.loads((ROOT / 'studio/production/plan.json').read_text())
        self.assertEqual(PS.validate_plan(plan, ROOT), [])


if __name__ == '__main__':
    unittest.main()
