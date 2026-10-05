"""Verify source binding, citation coverage, completed geometry and output-only scope."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'zapote').is_dir())
BASE = '212c497f9e762f87ed59ba38842dfaeedc7aa538'


def read(name: str):
    return json.loads((HERE/name).read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    result = {'status': 'INCOMPLETE', 'base': BASE, 'provider_model': 'OpenAI GPT-6'}
    (HERE/'verification.json').write_text(json.dumps(result, indent=2)+'\n')
    rows = read('overlaps.json')
    audit = read('citation-audit.json')
    inventory = read('inventory-check.json')
    require(dict(Counter(r['classification'] for r in rows)) == inventory['classes'], 'Class count mismatch')
    require(len(rows) == 78 and len({r['id'] for r in rows}) == 78, 'Rows missing or duplicate')
    require(all(r['prototype'] and r['decisions'] for r in rows), 'One side lacks a citation')
    for path, expected in inventory['cited_files_sha256'].items():
        raw = (ROOT/path).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, f'Source drift: {path}')
        committed = subprocess.check_output(['git','show',f'{BASE}:{path}'], cwd=ROOT)
        require(raw == committed, f'Uncommitted source: {path}')
    for item in audit:
        lines = (ROOT/item['path']).read_text().splitlines()
        require('\n'.join(lines[item['start']-1:item['end']]) == item['excerpt'], f'Citation drift: {item}')
    allowed_unmapped = {'D': {9}, 'S': {3,4,5,6,14,33,61,76,90}, 'F': {3,4,5,7,8,9,13,26,41,59}}
    uncovered = [r for r in read('coverage-index.json') if not r['rows'] and r['line'] not in allowed_unmapped[r['source']]]
    require(not uncovered, f'Unreviewed decision/status/finding lines: {uncovered}')
    for source in read('source-census.json'):
        require(hashlib.sha256((ROOT/source['path']).read_bytes()).hexdigest() == source['sha256'], f'Census drift: {source["path"]}')
    gates = read('repo-gates.json')
    require(gates['import_gate_exit'] == 0 and gates['regen_check_exit'] == 0, 'Repository gate did not pass')
    fit = read('fit-results.json')
    require(read('fit-status.json')['status'] == 'COMPLETE_NOMINAL_ONLY', 'Geometry incomplete')
    require(read('fit-status.json')['result_sha256'] == hashlib.sha256((HERE/'fit-results.json').read_bytes()).hexdigest(), 'Geometry receipt drift')
    require(fit['named_shapes'] == len(read('geometry-inventory.json')), 'Geometry census mismatch')
    for path, expected in fit['source_adapters_sha256'].items():
        require(hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected, f'CAD adapter drift: {path}')
    # Check hand-written preface citations and local artifact links as well as table citations.
    preface = (HERE/'REPORT-PREFACE.md').read_text()
    for path, start, end in re.findall(r'/blob/'+BASE+r'/([^\s)#]+)#L(\d+)(?:-L(\d+))?', preface):
        count = len((ROOT/path).read_text().splitlines())
        require(1 <= int(start) <= int(end or start) <= count, f'Bad preface citation {path}:{start}')
    for local in re.findall(r'\]\(([^\s)]+)\)', preface):
        if '://' not in local:
            require((HERE/local).exists(), f'Missing linked artifact {local}')
    require('78 overlaps: 33 AGREES, 2 CONTRADICTS, 32 ONE-SIDED, 11 SUPERSEDES' in preface, 'Summary count mismatch')
    # Source scope includes committed and uncommitted changes since the task base.
    changed = subprocess.check_output(['git','diff','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    prefix = str(HERE.relative_to(ROOT))+'/'
    require(all(p.startswith(prefix) for p in changed+untracked), 'Changes outside out-D27')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,'HEAD'],cwd=ROOT,check=True)
    result.update(status='PASS_ANALYSIS_PACKET', classes=inventory['classes'], rows=len(rows),
                  citations=len(audit), source_files=len(read('source-census.json')),
                  source_inputs_match_committed_base=True, only_out_D27_changed=True,
                  python_document_checks=sys.version.split()[0], geometry_status=fit['status'], repo_gates=gates,
                  geometry_result_sha256=hashlib.sha256((HERE/'fit-results.json').read_bytes()).hexdigest(),
                  source_interpretation='Human/agent source review; machine checks do not prove semantic completeness',
                  not_run=['firmware host or target tests', 'SPICE', 'FEM', 'Rust workspace/native bridge', 'physical hardware'])
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
