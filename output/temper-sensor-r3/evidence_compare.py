"""Compare sensor-r3 evidence across platforms.

The evidence reference platform is the remote box (linux x86_64): every
committed evidence file is regenerated there, and each carries a top-level
`reference_platform`. Re-running a study elsewhere (the Mac) gives the same
counts, classifications, hazard flags, latch rules and gate booleans, but the
closed-loop simulations drift in the last float digits (measured Linux vs Mac:
per-run latch times <= 0.4 s, temperatures <= 0.2 K, one chaotic steady T_c
1.8 K; summaries <= 1.6e-5 K; the D1 diagnostic < 1e-4 relative). So:

- same platform on both sides (or no platform on either): exact equality;
- different platforms: dict keys, list lengths, strings, booleans and ints
  exact; floats within a tolerance class chosen by what the number means:
    tight  (summaries, gates, thresholds): |a-b| <= 0.01 or <= 1e-4 relative;
    row    (per-run diagnostic rows):      |a-b| <= 0.5  or <= 1e-3 relative,
           plus at most `max_outliers` floats beyond that per file, each listed;
  hashes of platform-generated artifacts (evidence JSON, generated headers)
  and the library hash are not compared, and generated-artifact names are
  dropped from changed/dirty file lists, because their bytes legitimately
  differ by platform. Every hash of a hand-written source still compares exactly.

Text artifacts (generated headers, NOTES tables) compare line by line: the
non-numeric skeleton exactly, integer tokens exactly, decimal tokens with the
row (NOTES) or tight (headers) tolerance when the platforms differ.

    python3 evidence_compare.py file COMMITTED FRESH   # one file (.json, .json.gz, text)
    python3 evidence_compare.py tree [--base HEAD]     # every changed generated artifact vs base
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PLATFORM_KEY = "reference_platform"

TIGHT_ABS, TIGHT_REL = 0.01, 1e-4
ROW_ABS, ROW_REL = 0.5, 1e-3

# Platform-generated artifacts besides the evidence JSON under output/temper-sensor-r3.
GENERATED_TEXT = {
    "firmware/components/sensors/rim_ntc_table.h": "tight",
    "firmware/components/sensors/hs_ntc_table.h": "tight",
    "firmware/components/temper_hal/mock/mock_max31865_afe.h": "tight",
    "firmware/test/pan_temp_estimator_vectors.h": "tight",
    "firmware/test/contact_check_vectors.h": "tight",
    "output/temper-sensor-r3/leak-barrier/NOTES-t2.md": "row",
    "output/temper-sensor-r3/leak-barrier/NOTES-t3.md": "row",
}
GENERATED_BINARY = {"output/temper-sensor-r3/leak-barrier/setpoint-cap.png"}

# Per-run diagnostic rows: one closed-loop run each, so they carry the chaotic
# float drift. Everything else is a summary, gate or threshold (tight).
ROW_PATH = re.compile(
    r"(^|/)(leak_rows|benign_rows|rows|runs|cases|missed_example|hottest_case|d1_lost_runs|"
    r"lost_episodes|episodes|records|trace|traces|windows|late_thermal)(\[|/|$)")

# Per-file extras: more row paths (each an aggregate taken over per-run rows,
# so it inherits their drift) and the number of floats allowed past the row
# tolerance (each one is printed).
PROFILES: dict[str, dict] = {
    # T2's per-run rows file: every value is one closed-loop run's.
    "setpoint-cap-rows.json.gz": {"row_paths": r".", "max_outliers": 4},
}


def platform_id() -> str:
    return os.environ.get("TEMPER_EVIDENCE_PLATFORM") or f"{platform.system().lower()}-{platform.machine()}"


def stamp(obj):
    """Record the platform that generated this evidence (first key)."""
    if not isinstance(obj, dict):
        raise TypeError("evidence must be a JSON object to carry reference_platform")
    rest = {k: v for k, v in obj.items() if k != PLATFORM_KEY}
    return {PLATFORM_KEY: platform_id(), **rest}


def is_generated(name: str) -> bool:
    name = name.replace(os.sep, "/")
    if name in GENERATED_TEXT or name in GENERATED_BINARY:
        return True
    return name.startswith("output/temper-sensor-r3/") and (name.endswith(".json") or name.endswith(".json.gz"))


def load(path_or_bytes, name: str = ""):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    name = name or str(path_or_bytes)
    if name.endswith(".gz"):
        data = gzip.decompress(data)
    if name.endswith(".json") or name.endswith(".json.gz"):
        return json.loads(data)
    return data.decode("utf-8")


def _platform(obj):
    return obj.get(PLATFORM_KEY) if isinstance(obj, dict) else None


def cross_platform(a, b) -> bool:
    return _platform(a) != _platform(b)


class Result:
    def __init__(self):
        self.diffs: list[str] = []
        self.outliers: list[str] = []
        self.max_drift = {"tight": 0.0, "row": 0.0}

    @property
    def ok(self):
        return not self.diffs

    def __repr__(self):
        return f"Result(diffs={len(self.diffs)}, outliers={len(self.outliers)}, drift={self.max_drift})"


def _hash_key(path: str) -> bool:
    return "sha256" in path or path.endswith("/library") or "library_hash" in path


def _drop_generated(value):
    if isinstance(value, list) and all(isinstance(x, str) for x in value):
        return [x for x in value if not is_generated(x)]
    return value


def _float_ok(a: float, b: float, cls: str) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    d = abs(a - b)
    ab, rel = (TIGHT_ABS, TIGHT_REL) if cls == "tight" else (ROW_ABS, ROW_REL)
    return d <= ab or d <= rel * max(abs(a), abs(b))


NUM = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?|-?\d+[eE][-+]?\d+|-?\d+")


def _cmp_str(a: str, b: str, path: str, cls: str, res: Result):
    if a == b:
        return
    ta, tb = NUM.split(a), NUM.split(b)
    na, nb = NUM.findall(a), NUM.findall(b)
    if ta != tb or len(na) != len(nb):
        res.diffs.append(f"{path}: {a[:80]!r} != {b[:80]!r}")
        return
    for x, y in zip(na, nb):
        decimal = any(c in x + y for c in ".eE")
        if not decimal:
            if x != y:
                res.diffs.append(f"{path}: integer {x} != {y} in {a[:60]!r}")
            continue
        _cmp_float(float(x), float(y), path, cls, res)


def _cmp_float(a: float, b: float, path: str, cls: str, res: Result):
    d = abs(a - b)
    if _float_ok(a, b, cls):
        res.max_drift[cls] = max(res.max_drift[cls], d)
        return
    if cls == "row":
        res.outliers.append(f"{path}: {a!r} vs {b!r} (|d| {d:.4g})")
    else:
        res.diffs.append(f"{path}: {a!r} vs {b!r} (|d| {d:.4g}, tight)")


def _walk(a, b, path: str, cross: bool, res: Result, row_extra: re.Pattern | None):
    if not cross:
        if a != b or type(a) is not type(b):
            # Exact mode: report the first divergences only.
            if isinstance(a, dict) and isinstance(b, dict):
                for k in sorted(set(a) | set(b)):
                    if k not in a or k not in b:
                        res.diffs.append(f"{path}/{k}: key present on one side only")
                    elif a[k] != b[k]:
                        _walk(a[k], b[k], f"{path}/{k}", cross, res, row_extra)
            elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        _walk(x, y, f"{path}[{i}]", cross, res, row_extra)
            else:
                res.diffs.append(f"{path}: {str(a)[:80]} != {str(b)[:80]}")
        return
    cls = "row" if (ROW_PATH.search(path) or (row_extra and row_extra.search(path))) else "tight"
    if isinstance(a, dict) and isinstance(b, dict):
        keys = (set(a) | set(b)) - ({PLATFORM_KEY} if path == "" else set())
        for k in sorted(keys):
            sub = f"{path}/{k}"
            if k not in a or k not in b:
                res.diffs.append(f"{sub}: key present on one side only")
                continue
            # A generated artifact's bytes (and the compiled library) differ by
            # platform; hand-written source hashes still compare exactly.
            if _hash_key(sub) and (is_generated(k) or "library" in k):
                continue
            if re.search(r"(changed|dirty)", k):
                _walk(_drop_generated(a[k]), _drop_generated(b[k]), sub, cross, res, row_extra)
                continue
            _walk(a[k], b[k], sub, cross, res, row_extra)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            res.diffs.append(f"{path}: list length {len(a)} != {len(b)}")
            return
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, f"{path}[{i}]", cross, res, row_extra)
    elif isinstance(a, bool) or isinstance(b, bool):
        if a is not b:
            res.diffs.append(f"{path}: {a!r} != {b!r}")
    elif isinstance(a, int) and isinstance(b, int):
        if a != b:
            res.diffs.append(f"{path}: {a} != {b}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, int) != isinstance(b, int) and float(a) == float(b):
            return
        if isinstance(a, int) and isinstance(b, int):
            return
        _cmp_float(float(a), float(b), path, cls, res)
    elif isinstance(a, str) and isinstance(b, str):
        _cmp_str(a, b, path, cls, res)
    elif a is None and b is None:
        return
    else:
        res.diffs.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")


def compare(committed, fresh, *, name: str = "", cross: bool | None = None) -> Result:
    """Compare two loaded evidence objects (dicts/lists) or two texts."""
    res = Result()
    base = Path(name).name if name else ""
    prof = PROFILES.get(base, {})
    extra = re.compile(prof["row_paths"]) if prof.get("row_paths") else None
    if cross is None:
        cross = cross_platform(committed, fresh) if isinstance(committed, dict) else False
    if isinstance(committed, str) and isinstance(fresh, str):
        cls = next((c for k, c in GENERATED_TEXT.items() if name.replace(os.sep, "/").endswith(Path(k).name)), "tight")
        if not cross:
            if committed != fresh:
                res.diffs.append(f"{name}: text differs")
            return res
        la, lb = committed.splitlines(), fresh.splitlines()
        if len(la) != len(lb):
            res.diffs.append(f"{name}: {len(la)} != {len(lb)} lines")
            return res
        for i, (x, y) in enumerate(zip(la, lb)):
            _cmp_str(x, y, f"{name}:{i + 1}", cls, res)
    else:
        _walk(committed, fresh, "", cross, res, extra)
    allowed = prof.get("max_outliers", 0) if cross else 0
    if len(res.outliers) > allowed:
        res.diffs.extend(f"outlier beyond the row tolerance: {o}" for o in res.outliers)
    return res


def strip_keys(obj: dict, container: str, keys) -> dict:
    """Copy of `obj` without obj[container][k] for k in keys (toolchain strings)."""
    out = json.loads(json.dumps(obj, allow_nan=False))
    for k in keys:
        out.get(container, {}).pop(k, None)
    return out


def assert_same(committed, fresh, *, name: str, cross: bool | None = None, label: str = ""):
    """Raise ValueError listing the differences; print the outliers that were allowed."""
    res = compare(committed, fresh, name=name, cross=cross)
    for o in res.outliers if res.ok else []:
        print(f"{label or name}: allowed cross-platform outlier {o}")
    if not res.ok:
        shown = "\n  ".join(res.diffs[:20])
        more = f"\n  ... {len(res.diffs) - 20} more" if len(res.diffs) > 20 else ""
        raise ValueError(f"{label or name}: evidence differs ({len(res.diffs)}):\n  {shown}{more}")
    return res


def _git(*args, repo=REPO, binary=False):
    return subprocess.check_output(["git", *args], cwd=repo, text=not binary)


def _base_version(repo: Path, base: str, name: str):
    try:
        return _git("show", f"{base}:{name}", repo=repo, binary=True)
    except subprocess.CalledProcessError:
        return None


def compare_to_base(repo: Path, base: str, name: str) -> Result | None:
    """Working-tree file vs its version at `base`; None if absent at base."""
    old = _base_version(repo, base, name)
    if old is None:
        return None
    if name in GENERATED_BINARY:
        res = Result()
        return res  # rendered image: not compared across platforms
    a, b = load(old, name), load(repo / name, name)
    cross = cross_platform(a, b) if isinstance(a, dict) else True
    return compare(a, b, name=name, cross=cross)


def dirty_inputs(repo: Path, base: str, names) -> list[str]:
    """`git diff --name-only base -- names`, except generated artifacts that
    match their base version within the platform rule above."""
    names = [str(n) for n in names]
    out = _git("diff", "--name-only", base, "--", *names, repo=repo).splitlines()
    dirty = []
    for n in out:
        if is_generated(n):
            res = compare_to_base(repo, base, n)
            if res is not None and res.ok:
                continue
        dirty.append(n)
    return dirty


def tree(repo: Path, base: str) -> int:
    changed = _git("diff", "--name-only", base, repo=repo).splitlines()
    gen = [n for n in changed if is_generated(n)]
    other = [n for n in changed if not is_generated(n)]
    bad = 0
    for n in gen:
        res = compare_to_base(repo, base, n)
        if res is None:
            print(f"NEW  {n}")
            bad += 1
        elif res.ok:
            extra = f", {len(res.outliers)} allowed outliers" if res.outliers else ""
            print(f"ok   {n} (drift tight {res.max_drift['tight']:.3g}, row {res.max_drift['row']:.3g}{extra})")
            for o in res.outliers:
                print(f"       outlier {o}")
        else:
            bad += 1
            print(f"DIFF {n}")
            for d in res.diffs[:10]:
                print(f"       {d}")
    for n in other:
        print(f"src  {n} (not generated evidence: compare by review)")
    if bad:
        print(f"EVIDENCE DIFFERS FROM {base}: {bad} file(s)")
        return 1
    print(f"EVIDENCE MATCHES {base} ({len(gen)} regenerated file(s) within the platform rule)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("file")
    f.add_argument("committed", type=Path)
    f.add_argument("fresh", type=Path)
    f.add_argument("--cross", action="store_true", help="force cross-platform rules")
    t = sub.add_parser("tree")
    t.add_argument("--base", default="HEAD")
    t.add_argument("--repo", type=Path, default=REPO)
    args = ap.parse_args()
    if args.cmd == "tree":
        return tree(args.repo, args.base)
    a, b = load(args.committed), load(args.fresh)
    res = compare(a, b, name=str(args.committed), cross=True if args.cross else None)
    for o in res.outliers:
        print(f"outlier {o}")
    for d in res.diffs:
        print(f"DIFF {d}")
    print(("MATCH" if res.ok else "DIFFERS") + f" (drift tight {res.max_drift['tight']:.3g}, row {res.max_drift['row']:.3g})")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
