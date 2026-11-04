#!/usr/bin/env python3
"""Production planning utilities, not an animation/rendering engine.

python3 studio/tools/production_status.py validate
python3 studio/tools/production_status.py checklist --write
python3 studio/tools/production_status.py checklist --check
python3 studio/tools/production_status.py doctor --out studio/production/environment.json

Standard library only. Does not install packages, access the network, launch
Blender, publish files, or infer artistic approval from a green test suite.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / 'studio/production/plan.json'
DEFAULT_TRACKER = ROOT / 'docs/36-PRODUCTION-TRACKER.md'
STATUSES = {'planned', 'in_progress', 'blocked', 'review', 'done'}
STATUS_NAMES = {'planned': 'запланировано', 'in_progress': 'в работе',
                'blocked': 'блокер', 'review': 'на проверке', 'done': 'выполнено'}


def local_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('path must be a non-empty relative path')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'path must stay inside the repository: {value}')
    result = (root / path).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f'path escapes the repository: {value}')
    return result


def valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_plan(plan: dict, root: Path = ROOT) -> list[str]:
    errors = []
    if not isinstance(plan, dict):
        return ['plan must be an object']
    if type(plan.get('schema_version')) is not int or plan['schema_version'] != 1:
        errors.append('unsupported schema_version (expected integer 1)')
    for field in ('project', 'target', 'updated', 'next_task'):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            errors.append(f'{field}: required non-empty string')
    if not valid_date(plan.get('updated')):
        errors.append('updated: invalid ISO date')
    stages, gates = {}, {}
    for field, result in (('stages', stages), ('gates', gates)):
        values = plan.get(field)
        if not isinstance(values, list) or not values:
            errors.append(f'{field}: required non-empty list')
            continue
        for item in values:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id']:
                errors.append(f'{field}: invalid entry')
                continue
            if item['id'] in result:
                errors.append(f'{field}: duplicate id {item["id"]}')
            result[item['id']] = item
            if not isinstance(item.get('title'), str) or not item['title'].strip():
                errors.append(f'{field}: title required for {item["id"]}')
    values = plan.get('tasks')
    if not isinstance(values, list) or not values:
        return errors + ['tasks: required non-empty list']
    tasks = {}
    for task in values:
        if not isinstance(task, dict) or not isinstance(task.get('id'), str):
            errors.append('tasks: invalid task object')
            continue
        tid = task['id']
        if not re.fullmatch(r'[A-Z]+-\d{2}', tid):
            errors.append(f'{tid}: invalid task id')
        if tid in tasks:
            errors.append(f'duplicate task id: {tid}')
        tasks[tid] = task
        for field in ('title', 'owner'):
            if not isinstance(task.get(field), str) or not task[field].strip():
                errors.append(f'{tid}: {field} required')
        if not isinstance(task.get('status'), str) or task['status'] not in STATUSES:
            errors.append(f'{tid}: invalid status')
        if not isinstance(task.get('stage'), str) or task['stage'] not in stages:
            errors.append(f'{tid}: unknown stage')
        if not isinstance(task.get('gate'), str) or task['gate'] not in gates:
            errors.append(f'{tid}: unknown gate')
        if type(task.get('requires_approval')) is not bool:
            errors.append(f'{tid}: requires_approval must be boolean')
        if (task.get('requires_approval') and task.get('status') in ('review', 'done') and
                (not isinstance(task.get('revision'), str) or not task['revision'].strip())):
            errors.append(f'{tid}: visual review/done requires current revision')
        for field in ('acceptance', 'deliverables'):
            items = task.get(field)
            if not isinstance(items, list) or not items or any(not isinstance(x, str) or not x.strip() for x in items):
                errors.append(f'{tid}: {field} must be a non-empty string list')
        dependencies = task.get('depends_on')
        if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies):
            errors.append(f'{tid}: depends_on must be a string list')
        elif len(set(dependencies)) != len(dependencies):
            errors.append(f'{tid}: duplicate dependency')
        if task.get('status') == 'blocked' and (not isinstance(task.get('blocker'), str) or not task['blocker'].strip()):
            errors.append(f'{tid}: blocked task needs a blocker')
        evidence = task.get('evidence', [])
        if not isinstance(evidence, list):
            errors.append(f'{tid}: evidence must be a list')
            evidence = []
        approvals = 0
        for entry in evidence:
            if not isinstance(entry, dict) or entry.get('kind') not in ('file', 'approval'):
                errors.append(f'{tid}: invalid evidence entry')
                continue
            try:
                path = local_path(root, entry.get('path'))
            except ValueError as exc:
                errors.append(f'{tid}: {exc}')
                continue
            if not path.is_file():
                errors.append(f'{tid}: missing evidence file {entry.get("path")}')
                continue
            if entry['kind'] == 'approval':
                try:
                    record = json.loads(path.read_text(encoding='utf-8'))
                    if (not isinstance(record, dict) or record.get('task_id') != tid or
                            record.get('decision') != 'approved' or record.get('approver') != 'user' or
                            not isinstance(record.get('revision'), str) or not record['revision'].strip() or
                            record['revision'] != task.get('revision') or
                            not valid_date(record.get('approved_at'))):
                        raise ValueError('approval must identify task, user, date and approved revision')
                    approvals += 1
                except (OSError, ValueError) as exc:
                    errors.append(f'{tid}: invalid approval record: {exc}')
        if task.get('status') == 'done':
            if not evidence:
                errors.append(f'{tid}: done requires evidence')
            if task.get('requires_approval') and not approvals:
                errors.append(f'{tid}: done requires user approval record')
    for tid, task in tasks.items():
        deps = task.get('depends_on', [])
        if not isinstance(deps, list):
            continue
        for dep in deps:
            if not isinstance(dep, str) or dep not in tasks:
                errors.append(f'{tid}: unknown dependency {dep}')
            elif task.get('status') in ('in_progress', 'review', 'done') and tasks[dep].get('status') != 'done':
                errors.append(f'{tid}: active/done task has incomplete dependency {dep}')
    visiting, visited = set(), set()
    def walk(tid):
        if tid in visiting:
            errors.append(f'dependency cycle at {tid}')
            return
        if tid in visited:
            return
        visiting.add(tid)
        deps = tasks[tid].get('depends_on', [])
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str) and dep in tasks:
                    walk(dep)
        visiting.remove(tid)
        visited.add(tid)
    for tid in tasks:
        walk(tid)
    if not isinstance(plan.get('next_task'), str) or plan['next_task'] not in tasks:
        errors.append('next_task: unknown task')
    elif tasks[plan['next_task']].get('status') == 'done':
        errors.append('next_task: already done')
    return errors


def markdown(plan):
    """Pure deterministic projection of the authoritative task data."""
    tasks = plan['tasks']
    counts = Counter(t['status'] for t in tasks)
    lines = ['# 36 · Живой чек-лист производства', '',
             '> Сгенерировано из `studio/production/plan.json`. Не редактировать вручную.',
             '> Команда: `python3 studio/tools/production_status.py checklist --write`.', '',
             f'**Дата состояния:** {plan["updated"]} · **цель:** {plan["target"]}', '',
             f'Всего задач: **{len(tasks)}**. Выполнено: **{counts["done"]}**; '
             f'в работе: **{counts["in_progress"]}**; на проверке: **{counts["review"]}**; '
             f'с блокером: **{counts["blocked"]}**; запланировано: **{counts["planned"]}**.', '',
             '**Важно:** выполненные задачи документации/учёта не означают готовую '
             '3D-анимацию. Учёт задач не заменяет художественную приёмку шлюза.', '',
             f'**Следующая приоритетная задача: {plan["next_task"]}.**', '',
             'План: [33](33-PRODUCTION-PLAN.md) · архитектура: '
             '[34](34-ENGINE-ARCHITECTURE.md) · критерии: [35](35-QUALITY-GATES.md) · '
             'решения: [37](37-DECISION-LOG.md).', '', '## Состояние шлюзов', '',
             '| Шлюз | Задачи done | Состояние учёта |', '|---|---:|---|']
    for gate in plan['gates']:
        group = [t for t in tasks if t['gate'] == gate['id']]
        done = sum(t['status'] == 'done' for t in group)
        state = 'задачи закрыты; см. evidence' if group and done == len(group) else 'не закрыт'
        lines.append(f'| {gate["id"]} · {gate["title"]} | {done}/{len(group)} | {state} |')
    for stage in plan['stages']:
        lines += ['', f'## {stage["id"]} · {stage["title"]}', '']
        for task in tasks:
            if task['stage'] != stage['id']:
                continue
            tick = 'x' if task['status'] == 'done' else ' '
            deps = ', '.join(task['depends_on']) or 'нет'
            lines += [f'- [{tick}] **{task["id"]} — {task["title"]}**',
                      f'  - Статус: **{STATUS_NAMES[task["status"]]}**. '
                      f'Ответственность: {task["owner"]}. Шлюз: {task["gate"]}.',
                      f'  - Зависимости: {deps}.',
                      f'  - Результат: {"; ".join(task["deliverables"])}.',
                      f'  - Готово когда: {"; ".join(task["acceptance"])}.']
            if task.get('blocker'):
                lines.append(f'  - **Блокер:** {task["blocker"]}')
            if task['requires_approval']:
                lines.append('  - Нужна запись одобрения пользователем конкретной revision; молчание не считается одобрением.')
            if task.get('evidence'):
                links = [f'[{e["path"]}](../{e["path"]})' for e in task['evidence']]
                lines.append(f'  - Evidence: {", ".join(links)}.')
    lines += ['', '## Порядок обновления', '',
              '1. Изменить JSON: статус, зависимости, blocker, acceptance и evidence.',
              '2. Для done закрыть зависимости и приложить результат проверки; для visual approval — запись пользователя.',
              '3. Запустить validate, тесты и checklist --write, затем checklist --check.',
              '4. Добавить запись итерации в docs/37-DECISION-LOG.md: что сделано, что проверено, ограничения, следующий шаг.',
              '5. Не отмечать готовность движка/сцены по одному наличию файлов или unit tests.', '']
    return '\n'.join(lines)


def environment_report(record_date):
    packages = {}
    for name in ('Pillow', 'numpy', 'imageio-ffmpeg', 'opencv-python-headless'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    return {
        'schema_version': 1,
        'recorded_on': record_date,
        'scope': 'inventory only; no renderer/model/GPU smoke test performed',
        'python': platform.python_version(),
        'platform': platform.system(),
        'machine': platform.machine(),
        'binaries_in_path': {name: shutil.which(name) is not None for name in ('blender', 'ffmpeg')},
        'packages': packages,
        'gpu': 'not_probed',
        'renderer_smoke_test': 'not_run',
        'aligner_model_probe': 'not_run',
        'pilot_mp4_present': (ROOT / 'studio/out/pilot-letter-p.mp4').is_file(),
        'note': 'Absence from PATH is not proof of impossible installation or lack of GPU. '
                'imageio-ffmpeg may supply its own binary only after package installation/verification.'
    }


def main(argv=None):
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('validate')
    checklist = sub.add_parser('checklist')
    mode = checklist.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    checklist.add_argument('--out', type=Path, default=DEFAULT_TRACKER)
    doctor = sub.add_parser('doctor')
    doctor.add_argument('--out', type=Path)
    doctor.add_argument('--record-date', default=date.today().isoformat())
    doctor.add_argument('--require-renderer', action='store_true', help='Exit 2 if blender is absent; not a smoke test')
    args = parser.parse_args(argv)
    if args.command == 'doctor':
        if not valid_date(args.record_date):
            parser.error('--record-date must be an ISO date')
        report = environment_report(args.record_date)
        content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(content, encoding='utf-8')
        print(content, end='')
        return 2 if args.require_renderer and not report['binaries_in_path']['blender'] else 0
    try:
        plan = json.loads(args.plan.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'Cannot read plan: {exc}', file=sys.stderr)
        return 1
    errors = validate_plan(plan)
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    if args.command == 'validate':
        print(f'OK: {len(plan["tasks"])} tasks, dependencies/evidence/statuses valid')
        return 0
    content = markdown(plan)
    if args.check:
        if not args.out.is_file() or args.out.read_text(encoding='utf-8') != content:
            print('Checklist is missing or stale; run checklist --write', file=sys.stderr)
            return 1
        print('OK: checklist matches authoritative plan')
    elif args.write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content, encoding='utf-8')
        print(f'Wrote {args.out}')
    else:
        print(content, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
