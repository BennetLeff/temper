"""
Golden fixture diff engine for DSN/SES/JSON comparison.

Provides coordinate-aware comparison with per-boundary geometric tolerance.
Produces structured DiffReport with triage categories:
  BINARY       - structural mismatch (missing net, component, etc.)
  WITHIN_TOLERANCE - within threshold (informational)
  BEYOND_TOLERANCE - exceeds threshold (gate-failing)
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class DiffEntry:
    board: str
    stage: str
    category: str  # "BINARY" | "WITHIN_TOLERANCE" | "BEYOND_TOLERANCE"
    entity: str    # e.g., "net 'HV_IN'" or "component 'Q1'"
    field: str     # e.g., "X coordinate" or "pin count"
    golden_value: str
    candidate_value: str
    delta: Optional[float] = None
    tolerance: Optional[float] = None


@dataclass
class DiffReport:
    board: str
    stage: str
    passed: bool
    entries: list[DiffEntry] = field(default_factory=list)
    summary: str = ""

    def to_json(self) -> list:
        return [
            {
                'board': e.board,
                'stage': e.stage,
                'category': e.category,
                'entity': e.entity,
                'field': e.field,
                'golden_value': e.golden_value,
                'candidate_value': e.candidate_value,
                'delta': e.delta,
                'tolerance': e.tolerance,
            }
            for e in self.entries
        ]


class GoldenDiffParseError(Exception):
    """Raised when golden/candidate content cannot be parsed."""


def diff_golden(
    board: str,
    stage: str,
    golden_content: str,
    candidate_content: str,
    output_format: str,
    tolerance_mm: float,
) -> DiffReport:
    if output_format == 'dsn':
        return _diff_dsn(board, stage, golden_content, candidate_content, tolerance_mm)
    elif output_format == 'ses':
        return _diff_ses(board, stage, golden_content, candidate_content, tolerance_mm)
    elif output_format == 'json':
        return _diff_json(board, stage, golden_content, candidate_content, tolerance_mm)
    else:
        return DiffReport(
            board=board, stage=stage, passed=False,
            entries=[
                DiffEntry(
                    board=board, stage=stage, category='BINARY',
                    entity=f'format:{output_format}', field='output_format',
                    golden_value=output_format, candidate_value=output_format,
                )
            ],
            summary=f'Unknown output format: {output_format}',
        )


def _diff_dsn(board, stage, golden, candidate, tolerance):
    entries = []
    golden_places = _parse_dsn_places(golden)
    candidate_places = _parse_dsn_places(candidate)

    if golden_places is None or candidate_places is None:
        entries.append(
            DiffEntry(board=board, stage=stage, category='BINARY',
                      entity='dsn', field='parse',
                      golden_value='parse_ok' if golden_places else 'parse_fail',
                      candidate_value='parse_ok' if candidate_places else 'parse_fail'))
        return DiffReport(board=board, stage=stage, passed=False, entries=entries,
                          summary='DSN parse failure')

    all_refs = sorted(set(golden_places.keys()) | set(candidate_places.keys()))
    for ref in all_refs:
        gp = golden_places.get(ref)
        cp = candidate_places.get(ref)
        if gp is None:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f'component {ref}', field='presence',
                                     golden_value='missing', candidate_value='present'))
            continue
        if cp is None:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f'component {ref}', field='presence',
                                     golden_value='present', candidate_value='missing'))
            continue
        for axis, gv, cv in zip(['X', 'Y', 'rotation'], [gp[0], gp[1], gp[2]], [cp[0], cp[1], cp[2]]):
            if axis == 'rotation':
                delta = abs(gv - cv) % 360.0
                delta = min(delta, 360.0 - delta)
            else:
                delta = abs(gv - cv)
            cat = 'WITHIN_TOLERANCE' if delta <= tolerance else 'BEYOND_TOLERANCE'
            entries.append(DiffEntry(board=board, stage=stage, category=cat,
                                     entity=f'component {ref}', field=f'{axis} coordinate',
                                     golden_value=str(gv), candidate_value=str(cv),
                                     delta=delta, tolerance=tolerance))

    golden_nets = _parse_dsn_nets(golden)
    candidate_nets = _parse_dsn_nets(candidate)
    all_nets = sorted(set(golden_nets) | set(candidate_nets))
    for net in all_nets:
        gn = golden_nets.get(net)
        cn = candidate_nets.get(net)
        if gn is None:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f"net '{net}'", field='presence',
                                     golden_value='missing', candidate_value='present'))
        elif cn is None:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f"net '{net}'", field='presence',
                                     golden_value='present', candidate_value='missing'))
        elif gn != cn:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f"net '{net}'", field='pin_count',
                                     golden_value=str(gn), candidate_value=str(cn)))

    passed = not any(e.category in ('BINARY', 'BEYOND_TOLERANCE') for e in entries)
    failures = [e for e in entries if e.category in ('BINARY', 'BEYOND_TOLERANCE')]
    summary = f"{board}/{stage}: {'PASS' if passed else 'FAIL'} — {len(failures)} issues"
    return DiffReport(board=board, stage=stage, passed=passed, entries=entries, summary=summary)


def _parse_dsn_places(dsn_text):
    try:
        pattern = re.compile(r'\(\s*place\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+\S+\s+([\d.]+)')
        places = {}
        for m in pattern.finditer(dsn_text):
            ref = m.group(1)
            x = float(m.group(2)) / 100.0
            y = float(m.group(3)) / 100.0
            rot = float(m.group(4))
            places[ref] = (round(x, 6), round(y, 6), round(rot, 6))
        return places
    except Exception:
        return None


def _parse_dsn_nets(dsn_text):
    pattern = re.compile(r'\(\s*net\s+(\S+)\s+\(\s*pins\s+(.*?)\)')
    nets = {}
    for m in pattern.finditer(dsn_text):
        name = m.group(1)
        pins = m.group(2).split()
        nets[name] = len(pins)
    return nets


def _diff_ses(board, stage, golden, candidate, tolerance):
    entries = []
    golden_wires = _parse_ses_wires(golden)
    candidate_wires = _parse_ses_wires(candidate)

    if golden_wires is None or candidate_wires is None:
        entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                 entity='ses', field='parse',
                                 golden_value='parse_ok' if golden_wires else 'parse_fail',
                                 candidate_value='parse_ok' if candidate_wires else 'parse_fail'))
        return DiffReport(board=board, stage=stage, passed=False, entries=entries,
                          summary='SES parse failure')

    all_keys = sorted(set(golden_wires.keys()) | set(candidate_wires.keys()))
    for key in all_keys:
        gw = golden_wires.get(key)
        cw = candidate_wires.get(key)
        if gw is None:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f'wire_{key}', field='presence',
                                     golden_value='missing', candidate_value='present'))
            continue
        if cw is None:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=f'wire_{key}', field='presence',
                                     golden_value='present', candidate_value='missing'))
            continue
        for i, (gpt, cpt) in enumerate(zip(gw, cw)):
            delta = math.sqrt((gpt[0] - cpt[0]) ** 2 + (gpt[1] - cpt[1]) ** 2)
            cat = 'WITHIN_TOLERANCE' if delta <= tolerance else 'BEYOND_TOLERANCE'
            entries.append(DiffEntry(board=board, stage=stage, category=cat,
                                     entity=f'wire_{key}', field=f'point_{i}',
                                     golden_value=str(gpt), candidate_value=str(cpt),
                                     delta=delta, tolerance=tolerance))

    passed = not any(e.category in ('BINARY', 'BEYOND_TOLERANCE') for e in entries)
    failures = [e for e in entries if e.category in ('BINARY', 'BEYOND_TOLERANCE')]
    summary = f"{board}/{stage}: {'PASS' if passed else 'FAIL'} — {len(failures)} issues"
    return DiffReport(board=board, stage=stage, passed=passed, entries=entries, summary=summary)


def _parse_ses_wires(ses_text):
    try:
        pattern = re.compile(
            r'\(\s*wire\s+(\S+)\s+\(\s*path\s+\S+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)')
        wires = {}
        for idx, m in enumerate(pattern.finditer(ses_text)):
            net = m.group(1)
            x1, y1 = float(m.group(2)), float(m.group(3))
            x2, y2 = float(m.group(4)), float(m.group(5))
            wires[f'{net}_{idx}'] = [(x1, y1), (x2, y2)]
        return wires
    except Exception:
        return None


def _diff_json(board, stage, golden, candidate, tolerance):
    entries = []
    try:
        gj = json.loads(golden)
    except json.JSONDecodeError:
        entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                 entity='json', field='parse',
                                 golden_value='parse_fail', candidate_value='parse_ok'))
        return DiffReport(board=board, stage=stage, passed=False, entries=entries,
                          summary='Golden JSON parse failure')
    try:
        cj = json.loads(candidate)
    except json.JSONDecodeError:
        entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                 entity='json', field='parse',
                                 golden_value='parse_ok', candidate_value='parse_fail'))
        return DiffReport(board=board, stage=stage, passed=False, entries=entries,
                          summary='Candidate JSON parse failure')

    _json_diff_recursive(gj, cj, tolerance, board, stage, '', entries)

    passed = not any(e.category in ('BINARY', 'BEYOND_TOLERANCE') for e in entries)
    failures = [e for e in entries if e.category in ('BINARY', 'BEYOND_TOLERANCE')]
    summary = f"{board}/{stage}: {'PASS' if passed else 'FAIL'} — {len(failures)} issues"
    return DiffReport(board=board, stage=stage, passed=passed, entries=entries, summary=summary)


def _json_diff_recursive(golden_val, candidate_val, tolerance, board, stage, path, entries):
    if type(golden_val) != type(candidate_val):
        entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                 entity=path or 'root', field='type',
                                 golden_value=str(type(golden_val).__name__),
                                 candidate_value=str(type(candidate_val).__name__)))
        return

    if isinstance(golden_val, dict):
        all_keys = sorted(set(golden_val.keys()) | set(candidate_val.keys()))
        for k in all_keys:
            new_path = f'{path}.{k}' if path else k
            if k not in golden_val:
                entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                         entity=new_path, field='presence',
                                         golden_value='missing', candidate_value='present'))
            elif k not in candidate_val:
                entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                         entity=new_path, field='presence',
                                         golden_value='present', candidate_value='missing'))
            else:
                _json_diff_recursive(golden_val[k], candidate_val[k], tolerance,
                                    board, stage, new_path, entries)
    elif isinstance(golden_val, list):
        if len(golden_val) != len(candidate_val):
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=path or 'root', field='length',
                                     golden_value=str(len(golden_val)),
                                     candidate_value=str(len(candidate_val))))
        else:
            for i, (gv, cv) in enumerate(zip(golden_val, candidate_val)):
                _json_diff_recursive(gv, cv, tolerance, board, stage, f'{path}[{i}]', entries)
    elif isinstance(golden_val, (int, float)):
        if isinstance(golden_val, float) and isinstance(candidate_val, float):
            delta = abs(golden_val - candidate_val)
            cat = 'WITHIN_TOLERANCE' if delta <= tolerance else 'BEYOND_TOLERANCE'
            entries.append(DiffEntry(board=board, stage=stage, category=cat,
                                     entity=path or 'root', field='value',
                                     golden_value=str(golden_val), candidate_value=str(candidate_val),
                                     delta=delta, tolerance=tolerance))
        elif golden_val != candidate_val:
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=path or 'root', field='value',
                                     golden_value=str(golden_val), candidate_value=str(candidate_val)))
    else:
        if str(golden_val) != str(candidate_val):
            entries.append(DiffEntry(board=board, stage=stage, category='BINARY',
                                     entity=path or 'root', field='value',
                                     golden_value=str(golden_val), candidate_value=str(candidate_val)))
