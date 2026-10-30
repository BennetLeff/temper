"""Fab-house limits as a KiCad DRC pass (port of zapote's fab pass: zapote-drc fab_rules.rs, zapote-harness
fab_check.rs, tools/fab_board_copy.py and tools/make_fab_selftest_board.py on origin/main, 2026-10-29).

A fab profile (jlc/data/fab-profiles/*.json, schema zapote.fab-profile.v1) holds the vendor's limits, each with
the vendor's own sentence.  rules() turns them into KiCad custom rules; run() checks a board against them:

  1. a copy of the board without pad/footprint local clearances (KiCad applies those before any custom rule)
     and with the profile's solder-mask web as the board minimum (kicad_scripts/fab_board_copy.py);
  2. the rules as the copy's only .kicad_dru, no .kicad_pro: the board's own rules stay in its own DRC;
  3. the same rules on a self-test board on which every rule must fire (kicad_scripts/fab_selftest_board.py):
     KiCad ignores a malformed .kicad_dru silently, so a rule that does not fire there was not applied;
  4. kicad-cli pcb drc on both; findings are the violations KiCad attributes to a rule named RULE_PREFIX...

KiCad 10.0.4 behaviour this relies on (measured by zapote 2026-10-08, and by the self-test here): when several
custom rules match, the last one wins even if it is looser, so overlapping rules are written loosest first
(general spacing, then the pad rows; hole rules by limit, ascending; pad hole-to-hole, then via-to-via);
silk_clearance scoped to pads is reported as silk_over_copper; the mask web has no custom constraint and is
reported as solder_mask_bridge once the board minimum is set.

Pure Python 3.9 except run(), which needs kicad-cli and KiCad's Python.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

PROFILES = Path(__file__).resolve().parent / "jlc" / "data" / "fab-profiles"
SCRIPTS = Path(__file__).resolve().parent / "kicad_scripts"
RULE_PREFIX = "boardkit fab"
KICAD_CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
KICAD_PYTHON = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
NOT_COVERED = [
    "silkscreen graphic line width (KiCad constrains text strokes only)",
    "board size against maximum_board_mm (read the outline: gerber.outline)",
    "JLC's 0.09 mm local BGA pad spacing (the stricter general rows are kept)",
]


def profile(name):
    """A profile by name ('jlcpcb-4layer-1oz') or path."""
    path = Path(name) if str(name).endswith(".json") else PROFILES / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _numbers(v):
    return v if isinstance(v, list) else [v]


def validate(prof, source_text=None):
    """Problems with a profile: a limit without a quote, a quote that does not state the number, and (with the
    page text) a quote that is not a verbatim substring of it.  [] when sound."""
    out = []
    for key, value in prof["limits"].items():
        quote = prof["quotes"].get(key)
        if not quote:
            out.append(f"{key}: no quote")
            continue
        if source_text is not None and quote not in source_text:
            out.append(f"{key}: quote not in the source text")
        if key in prof.get("derivations", {}):
            continue
        stated = {float(m) for m in re.findall(r"\d+(?:\.\d+)?", quote)}
        if not all(float(n) in stated for n in _numbers(value)):
            out.append(f"{key}: {value} not stated in {quote!r}")
    return out


def _rule(name, scope, constraint, text, violation=None):
    name = f"{RULE_PREFIX} {name}"
    return {
        "name": name,
        "constraint": constraint,
        "violation": violation or constraint,
        "text": f'(rule "{name}"{scope} (constraint {constraint} {text}))',
    }


def _min(v):
    return f"(min {v}mm)"


PTH = "A.Type == 'Pad' && A.Pad_Type == 'Through-hole'"
NPTH = "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical'"


def rules(limits):
    """The KiCad custom rules for a profile's limits, in .kicad_dru order (see the module docstring)."""
    L = limits.get
    out = []
    if L("minimum_copper_clearance_mm") is not None:
        out.append(
            _rule("copper clearance", "", "clearance", _min(L("minimum_copper_clearance_mm")))
        )
    if L("minimum_pad_to_track_mm") is not None:
        out.append(
            _rule(
                "pad to track",
                " (condition \"A.Type == 'Pad' && B.Type == 'Track'\")",
                "clearance",
                _min(L("minimum_pad_to_track_mm")),
            )
        )
    if L("minimum_smd_pad_to_pad_mm") is not None:
        cond = "A.Type == 'Pad' && A.Pad_Type == 'SMD' && B.Type == 'Pad' && B.Pad_Type == 'SMD'"
        out.append(
            _rule(
                "SMD pad to pad",
                f' (condition "{cond}")',
                "clearance",
                _min(L("minimum_smd_pad_to_pad_mm")),
            )
        )
    holes = [
        (v, _rule(name, f'{layer} (condition "{cond}")', "hole_clearance", _min(v)))
        for name, layer, cond, v in (
            ("via hole to copper", "", "A.Type == 'Via'", L("minimum_via_hole_to_copper_mm")),
            ("PTH hole to copper", "", PTH, L("minimum_pth_hole_to_copper_mm")),
            ("NPTH hole to copper", "", NPTH, L("minimum_npth_hole_to_copper_mm")),
            (
                "inner PTH hole to copper",
                " (layer inner)",
                PTH,
                L("minimum_inner_pth_hole_to_copper_mm"),
            ),
        )
        if v is not None
    ]
    out += [r for _, r in sorted(holes, key=lambda h: h[0])]
    if L("minimum_hole_clearance_mm") is not None:
        out.append(_rule("hole to hole", "", "hole_to_hole", _min(L("minimum_hole_clearance_mm"))))
    if L("minimum_via_hole_clearance_mm") is not None:
        out.append(
            _rule(
                "via hole to via hole",
                " (condition \"A.Type == 'Via' && B.Type == 'Via'\")",
                "hole_to_hole",
                _min(L("minimum_via_hole_clearance_mm")),
            )
        )
    if L("minimum_copper_to_edge_mm") is not None:
        out.append(
            _rule(
                "copper to edge",
                "",
                "edge_clearance",
                _min(L("minimum_copper_to_edge_mm")),
                "copper_edge_clearance",
            )
        )
    if L("minimum_track_width_mm") is not None:
        out.append(_rule("track width", "", "track_width", _min(L("minimum_track_width_mm"))))
    if L("minimum_via_annular_ring_mm") is not None:
        out.append(
            _rule(
                "via ring",
                " (condition \"A.Type == 'Via'\")",
                "annular_width",
                _min(L("minimum_via_annular_ring_mm")),
            )
        )
    if L("minimum_annular_ring_mm") is not None:
        out.append(
            _rule(
                "PTH ring",
                f' (condition "{PTH}")',
                "annular_width",
                _min(L("minimum_annular_ring_mm")),
            )
        )
    if L("minimum_via_drill_mm") is not None:
        out.append(
            _rule(
                "via drill",
                " (condition \"A.Type == 'Via'\")",
                "hole_size",
                _min(L("minimum_via_drill_mm")),
                "drill_out_of_range",
            )
        )
    pth_drill = " ".join(
        f"({k} {v}mm)"
        for k, v in (("min", L("minimum_pth_drill_mm")), ("max", L("maximum_pth_drill_mm")))
        if v is not None
    )
    if (
        pth_drill
    ):  # one rule: a separate max rule with the same condition would win over the min (last match)
        out.append(
            _rule(
                "PTH drill", f' (condition "{PTH}")', "hole_size", pth_drill, "drill_out_of_range"
            )
        )
    if L("minimum_npth_drill_mm") is not None:
        out.append(
            _rule(
                "NPTH drill",
                f' (condition "{NPTH}")',
                "hole_size",
                _min(L("minimum_npth_drill_mm")),
                "drill_out_of_range",
            )
        )
    for suffix, layer in (("", "F.SilkS"), (" B", "B.SilkS")):
        if L("minimum_silk_text_height_mm") is not None:
            out.append(
                _rule(
                    f"silk text height{suffix}",
                    f' (layer "{layer}")',
                    "text_height",
                    _min(L("minimum_silk_text_height_mm")),
                )
            )
        if L("minimum_silk_line_width_mm") is not None:
            out.append(
                _rule(
                    f"silk text thickness{suffix}",
                    f' (layer "{layer}")',
                    "text_thickness",
                    _min(L("minimum_silk_line_width_mm")),
                )
            )
    if L("minimum_pad_to_silk_mm") is not None:
        out.append(
            _rule(
                "pad to silk",
                " (condition \"A.Type == 'Pad' || B.Type == 'Pad'\")",
                "silk_clearance",
                _min(L("minimum_pad_to_silk_mm")),
                "silk_over_copper",
            )
        )
    if L("minimum_solder_mask_web_mm") is not None:  # a board setting, no .kicad_dru text
        out.append(
            {
                "name": f"{RULE_PREFIX} solder mask web",
                "constraint": "solder_mask_min_width",
                "violation": "solder_mask_bridge",
                "text": "",
            }
        )
    return out


def dru_text(rule_list):
    return "(version 1)\n" + "\n".join(r["text"] for r in rule_list if r["text"]) + "\n"


_RULE_RE = re.compile(r"\(rule '([^']+)'")


def attribute(report, rule_list):
    """kicad-cli DRC json -> {rule name: [violations]} for the rules of this pass.  A violation names its rule
    in the description ("(rule 'boardkit fab ...' ...)"); the mask web is matched by violation type."""
    by_name = {r["name"]: [] for r in rule_list}
    web = next((r["name"] for r in rule_list if not r["text"]), None)
    for v in report.get("violations", []):
        m = _RULE_RE.search(v.get("description", ""))
        if m and m.group(1) in by_name:
            by_name[m.group(1)].append(v)
        elif web and v.get("type") == "solder_mask_bridge":
            by_name[web].append(v)
    return by_name


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _kicad_python(python, script, *args):
    r = subprocess.run(
        [python, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True
    )
    if r.returncode != 0:
        raise RuntimeError(f"{script} failed: {r.stderr[-2000:]}")
    return r.stdout


def _drc(kicad_cli, board, out_json):
    r = subprocess.run(
        [
            kicad_cli,
            "pcb",
            "drc",
            "--severity-all",
            "--all-track-errors",
            "--format",
            "json",
            "--output",
            str(out_json),
            str(board),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not Path(out_json).exists():
        raise RuntimeError(f"kicad-cli drc failed on {board}: {r.stderr[-2000:]}")
    return json.loads(Path(out_json).read_text())


def _stage(path, rule_text):
    for suffix in (".kicad_pro", ".kicad_prl"):
        path.with_suffix(suffix).unlink(missing_ok=True)
    path.with_suffix(".kicad_dru").write_text(rule_text)


def run(board, prof, out, kicad_cli=KICAD_CLI, kicad_python=KICAD_PYTHON):
    """Check board against profile prof (a dict or name) in the new directory out.  -> report dict with
    'pass', 'selftest' (rules that did not fire on the self-test board: must be empty), 'findings' per rule,
    and the receipts (hashes of board, rules and reports, KiCad version, cleared local clearances)."""
    prof = profile(prof) if isinstance(prof, str) else prof
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    rule_list = rules(prof["limits"])
    text = dru_text(rule_list)
    web = prof["limits"].get("minimum_solder_mask_web_mm")
    version = subprocess.run(
        [kicad_cli, "--version"], capture_output=True, text=True
    ).stdout.strip()

    (out / "selftest").mkdir()
    selftest = out / "selftest" / "fab_selftest.kicad_pcb"
    _kicad_python(kicad_python, "fab_selftest_board.py", selftest)
    _kicad_python(kicad_python, "fab_board_copy.py", selftest, selftest, *([web] if web else []))
    _stage(selftest, text)
    fired = attribute(_drc(kicad_cli, selftest, out / "selftest" / "drc.json"), rule_list)
    silent = sorted(n for n, v in fired.items() if not v)

    (out / "board").mkdir()
    copy = out / "board" / Path(board).name
    cleared = json.loads(
        _kicad_python(kicad_python, "fab_board_copy.py", board, copy, *([web] if web else []))
    )
    _stage(copy, text)
    found = attribute(_drc(kicad_cli, copy, out / "board" / "drc.json"), rule_list)
    findings = {
        n: [
            {
                "type": v["type"],
                "description": v["description"],
                "items": [i.get("description") for i in v.get("items", [])],
            }
            for v in vs
        ]
        for n, vs in found.items()
        if vs
    }
    report = {
        "pass": not silent and not findings,
        "profile": prof["name"],
        "profile_read": prof.get("read"),
        "board": str(board),
        "board_sha256": _sha(board),
        "rules_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "kicad": version,
        "rules": [r["name"] for r in rule_list],
        "selftest_silent_rules": silent,
        "findings": findings,
        "counts": {n: len(v) for n, v in findings.items()},
        "cleared_local_clearances": cleared["cleared"],
        "solder_mask_min_web_mm": cleared["solder_mask_min_web_mm"],
        "not_covered": NOT_COVERED,
    }
    (out / "fab-check.json").write_text(json.dumps(report, indent=1) + "\n")
    return report


def summary(report):
    lines = [
        f"fab pass {report['profile']} (read {report['profile_read']}): "
        f"{'PASS' if report['pass'] else 'FAIL'}  [{report['kicad']}]"
    ]
    if report["selftest_silent_rules"]:
        lines.append(
            f"  rules that did not fire on the self-test board: {report['selftest_silent_rules']}"
        )
    for name, n in sorted(report["counts"].items()):
        lines.append(f"  {n:4}  {name}")
    return "\n".join(lines)
