#!/usr/bin/env python3
"""Fabricated-MPN CI gate: fail closed on invented parts and value/MPN drift.

Motivation (docs/evidence/2026-07-27-fabricated-mpn-audit.md): four fabricated
components were found in this design, every one by accident while looking for
something else --

  1. EKZE251ELL332MM40S (bus capacitor) -- did not exist at any distributor.
  2. DE2E3KH221MA3B (X2 safety cap) -- MPN unfindable *and* the value was
     wrong by 1000x (Murata's "221" suffix decodes to 220 pF; the BOM called
     it 220 nF).
  3. A third case recorded in the 2026-07-26 BOM availability sweep.
  4. ERA-3AEB6132V / 61.3 kOhm (modules.ato) -- 61.3 kOhm is not an E96 *or*
     E192 value (neighbours 60.4, 61.2, 61.9 kOhm) and the MPN is in neither
     DigiKey's nor Mouser's catalogue. Value and MPN were internally
     consistent with each other -- and both invented.

The common signature: a non-standard passive value (not an E6/E12/E24/E48/
E96/E192 member) and/or an MPN whose own value-encoding disagrees with the
component's declared value. Both checks are offline and need no network
access -- that is what makes them viable as a hard, always-on CI gate.

What this gate checks, over every ``Resistor``/``Capacitor`` value+mpn pair
declared in ``elec/src/*.ato``:

  1. E-SERIES MEMBERSHIP -- the declared value's mantissa must belong to the
     standard series appropriate to its declared tolerance (E6/E12/E24/E48/
     E96/E192; unspecified tolerance falls back to "member of any standard
     series"). Non-members fail, and the nearest legal neighbours in that
     series are printed.
  2. MPN VALUE-DECODE AGREEMENT -- where the MPN's manufacturer-prefix family
     is recognised (Yageo RC/RSF, Vishay CRCW/CRGP, Panasonic ERA-xAEB,
     Murata/Kemet 3-digit-EIA-coded MLCCs), the value the MPN itself encodes
     must agree with the declared value within 2%. Unrecognised prefixes are
     counted and reported as UNCHECKED -- never silently treated as passing.

Both checks can be suppressed per-line by a *hand-curated* allowlist
(mpn-fabrication-allowlist.yaml) that this script only ever reads. There is
no ``--init``/``--regenerate`` mode: check_typecheck_gate.py's auto-resynced
allowlist is exactly how a live TypeError survived in CI for three days here
(commit history, 2026-07-2x); an allowlist that can bulk-absorb new findings
without a human writing the reason is not a safety net, it's a hole with a
sign over it.

Anti-vacuity (METHODOLOGY.md failure class 4): zero ``.ato`` files found,
zero parts parsed, or a missing/unparseable allowlist are all hard failures
-- never a silent pass. "0 parts inspected, 0 violations" is a FAIL here, not
a PASS.

Exit codes:
  0 - OK (all resistor/capacitor values are E-series members or allowlisted,
      all decodable MPNs agree with their declared value or are allowlisted)
  3 - Violations found (E-series non-membership or MPN/value disagreement,
      not covered by the allowlist)
  5 - Gate error (no .ato files found, zero parts parsed, allowlist present
      but unparseable, or any other tool-level failure) -- never a pass

Usage:
  uv run python scripts/mpn_fabrication_gate.py
  uv run python scripts/mpn_fabrication_gate.py --ato-glob 'elec/src/*.ato'
  uv run python scripts/mpn_fabrication_gate.py --allowlist mpn-fabrication-allowlist.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import math
import re
from dataclasses import dataclass, field

from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root

REPO_ROOT = find_repo_root()

DEFAULT_ATO_GLOB = "elec/src/*.ato"
DEFAULT_ALLOWLIST = "mpn-fabrication-allowlist.yaml"

# ---------------------------------------------------------------------------
# Parsing: pull (ref, declared value, declared tolerance, mpn) tuples out of
# atopile source. The convention this codebase uses (checked across all 172
# `.mpn =` lines in elec/src/*.ato) is:
#
#     <ref>.value = <number><unit> [+/- <tol>%]
#     ...
#     <ref>.mpn = "<MPN>"
#
# with the mpn line following the value line for the same <ref> within the
# same module block, not necessarily on the very next line (footprint,
# power_rating, dielectric, etc. can sit in between). Variable names are
# reused across module bodies (e.g. every OCP/OVP/thermal comparator has its
# own r_ref_top), so pairing is done by "most recently seen value for this
# ref name", which is correct as long as a ref's own value line always
# precedes its own mpn line in file order -- true throughout this codebase
# and asserted implicitly by the mismatch/E-series findings in the audit
# matching hand-verification against the source.
# ---------------------------------------------------------------------------

VALUE_RE = re.compile(
    r"^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\.value\s*=\s*(?P<num>[\d.]+)\s*(?P<unit>[A-Za-z]+)"
    r"(?:\s*\+/-\s*(?P<tol>[\d.]+)\s*%)?\s*$"
)
MPN_RE = re.compile(r'^\s*(?P<var>[A-Za-z_][A-Za-z0-9_]*)\.mpn\s*=\s*"(?P<mpn>[^"]+)"')

UNIT_MULT = {
    "ohm": 1.0,
    "kohm": 1e3,
    "Mohm": 1e6,
    "mohm": 1e-3,
    "pF": 1e-12,
    "nF": 1e-9,
    "uF": 1e-6,
    "F": 1.0,
}


def _kind_of(unit: str) -> str | None:
    if unit is None:
        return None
    if "ohm" in unit:
        return "R"
    if unit in ("pF", "nF", "uF", "F"):
        return "C"
    return None


@dataclass
class ParsedPart:
    file: str
    line: int
    ref: str
    mpn: str
    kind: str  # "R" or "C"
    declared_value: float  # base unit: ohms or farads
    declared_tol_pct: float | None


def parse_ato_file(path: Path, repo_root: Path) -> list[ParsedPart]:
    """Extract every (ref, declared R/C value, mpn) triple from one .ato file."""
    parts: list[ParsedPart] = []
    pending: dict[str, tuple[float, str, float | None]] = {}
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return parts
    rel = str(path.relative_to(repo_root))
    for i, line in enumerate(lines, start=1):
        m = VALUE_RE.match(line)
        if m:
            unit = m.group("unit")
            if unit not in UNIT_MULT:
                continue
            tol = m.group("tol")
            pending[m.group("var")] = (
                float(m.group("num")) * UNIT_MULT[unit],
                unit,
                float(tol) if tol is not None else None,
            )
            continue
        m2 = MPN_RE.match(line)
        if m2:
            var = m2.group("var")
            val = pending.get(var)
            if val is None:
                continue
            base_val, unit, tol = val
            kind = _kind_of(unit)
            if kind not in ("R", "C"):
                continue
            parts.append(
                ParsedPart(
                    file=rel,
                    line=i,
                    ref=var,
                    mpn=m2.group("mpn"),
                    kind=kind,
                    declared_value=base_val,
                    declared_tol_pct=tol,
                )
            )
    return parts


def parse_all(ato_glob: str, repo_root: Path) -> list[ParsedPart]:
    parts: list[ParsedPart] = []
    for path in sorted(repo_root.glob(ato_glob)):
        parts.extend(parse_ato_file(path, repo_root))
    return parts


# ---------------------------------------------------------------------------
# E-series (IEC 60063). Generated by the standard rounding construction
# (round(10**(k/n), 3 significant figures) for k in range(n)), which is how
# every E96/E192 reference table in circulation is built. Validated against
# the known-good anchor from case 4 of the audit: for a 0.1%-tolerance part
# at 61.3 kOhm, this construction yields neighbours 60.4/61.2/61.9 kOhm --
# exactly the trio the case-4 finding names, and 61.3 is confirmed absent.
# ---------------------------------------------------------------------------

E6 = [1.0, 1.5, 2.2, 3.3, 4.7, 6.8]
E12 = [1.0, 1.2, 1.5, 1.8, 2.2, 2.7, 3.3, 3.9, 4.7, 5.6, 6.8, 8.2]
E24 = [
    1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0,
    3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1,
]


def _gen_series(n: int) -> list[float]:
    vals = set()
    for k in range(n):
        v = 10 ** (k / n)
        exp = math.floor(round(math.log10(v), 9))
        factor = 10 ** (2 - exp)
        vals.add(round(round(v * factor) / factor, 6))
    return sorted(vals)


E48 = _gen_series(48)
E96 = _gen_series(96)
E192 = _gen_series(192)

SERIES = {"E6": E6, "E12": E12, "E24": E24, "E48": E48, "E96": E96, "E192": E192}
# Broadest-first order so the "any series" fallback reports the tightest
# series a value happens to satisfy.
ALL_SERIES_NAMES = ("E6", "E12", "E24", "E48", "E96", "E192")


def series_for_tolerance(tol_pct: float | None) -> str | None:
    if tol_pct is None:
        return None
    if tol_pct >= 20:
        return "E6"
    if tol_pct >= 10:
        return "E12"
    if tol_pct >= 5:
        return "E24"
    if tol_pct >= 2:
        return "E48"
    if tol_pct >= 1:
        return "E96"
    return "E192"


def _mantissa_decade(value: float) -> tuple[float, int]:
    if value == 0:
        return (0.0, 0)
    exp = math.floor(math.log10(value))
    mant = round(value / (10**exp), 6)
    if mant >= 9.999999:
        mant, exp = mant / 10, exp + 1
    return mant, exp


def in_series(value: float, series_name: str, rel_tol: float = 1e-3) -> bool:
    mant, _ = _mantissa_decade(value)
    return any(abs(s - mant) / s < rel_tol for s in SERIES[series_name])


def nearest_in_series(value: float, series_name: str, n: int = 3) -> list[float]:
    mant, exp = _mantissa_decade(value)
    candidates = [s * (10**e) for e in (exp - 1, exp, exp + 1) for s in SERIES[series_name]]
    candidates.sort(key=lambda c: abs(c - value))
    return candidates[:n]


# ---------------------------------------------------------------------------
# MPN value decoders. Two families of manufacturer value-encoding, both
# validated against the audit's hand-verified findings (see
# docs/evidence/2026-07-27-fabricated-mpn-audit.md):
#
#   (a) "R/K/M inline decimal" -- Yageo RC/RSF, Vishay CRCW/CRGP. The
#       multiplier letter (R=x1, K=x1e3, M=x1e6) also marks the decimal
#       point, e.g. "2K2" -> 2.2 kOhm, "430K" -> 430 kOhm, "4R99" -> 4.99 Ohm.
#   (b) "3-digit EIA + tolerance letter" -- Murata/Kemet-style MLCC part
#       numbers and Panasonic ERA-xAEB thin-film resistors. The last digit
#       of a digits-only run is a power-of-ten multiplier applied to the
#       leading digits, in the family's base unit (pF for MLCCs, ohms for
#       ERA resistors), e.g. "104" -> 10*10**4 = 100000 pF = 100 nF;
#       "6192" -> 619*10**2 = 61900 Ohm = 61.9 kOhm.
# ---------------------------------------------------------------------------

TOL_LETTER_PCT = {"B": 0.1, "C": 0.25, "D": 0.5, "F": 1.0, "G": 2.0, "J": 5.0, "K": 10.0, "M": 20.0, "Z": 20.0}


@dataclass
class Decoded:
    value: float  # base unit (ohms for R, farads for C)
    kind: str  # "R" or "C"
    tol_pct: float | None
    family: str


def _decode_rkm(code: str) -> float | None:
    m = re.match(r"^(\d*)([RKMrkm])(\d*)$", code)
    if not m:
        return None
    intpart, letter, fracpart = m.groups()
    mult = {"R": 1.0, "K": 1e3, "M": 1e6}[letter.upper()]
    s = (intpart or "0") + ("." + fracpart if fracpart else "")
    try:
        return float(s) * mult
    except ValueError:
        return None


def _decode_eia3(code: str) -> float | None:
    if not code.isdigit() or len(code) < 2:
        return None
    try:
        return float(code[:-1]) * (10 ** int(code[-1]))
    except ValueError:
        return None


def decode_mpn(mpn: str) -> Decoded | None:
    """Return the value+kind the MPN itself encodes, or None if the
    manufacturer-prefix family isn't recognised (UNCHECKED, not a pass)."""
    m = re.match(r"^RC(\d{4})([A-Z])[A-Z]?-(\d{2})([0-9A-Za-z]+)L$", mpn)
    if m:
        val = _decode_rkm(m.group(4))
        if val is not None:
            return Decoded(val, "R", TOL_LETTER_PCT.get(m.group(2).upper()), "Yageo RC")

    m = re.match(r"^RSF\d{3}([A-Z])[A-Z]-\d{2}-([0-9A-Za-z]+)$", mpn)
    if m:
        val = _decode_rkm(m.group(2))
        if val is not None:
            return Decoded(val, "R", TOL_LETTER_PCT.get(m.group(1).upper()), "Yageo RSF")

    m = re.match(r"^CRCW(\d{4})([0-9A-Za-z]+?)([FJGD])([A-Z]{2,3})$", mpn)
    if m:
        val = _decode_rkm(m.group(2))
        if val is not None:
            return Decoded(val, "R", TOL_LETTER_PCT.get(m.group(3).upper()), "Vishay CRCW")

    m = re.match(r"^CRGP(\d{4})([FJGD])([0-9A-Za-z]+)$", mpn)
    if m:
        val = _decode_rkm(m.group(3))
        if val is not None:
            return Decoded(val, "R", TOL_LETTER_PCT.get(m.group(2).upper()), "Vishay CRGP")

    m = re.match(r"^ERA-(\d)AEB(\d{3,4})V$", mpn)
    if m:
        val = _decode_eia3(m.group(2))
        if val is not None:
            # AEB is Panasonic's 0.1%-tolerance ERA sub-designation.
            return Decoded(val, "R", 0.1, "Panasonic ERA-xAEB")

    if re.match(r"^(GRM|GCM)\d", mpn) or re.match(r"^C\d{4}C", mpn):
        m2 = re.search(r"(\d{3})([KJMZ])", mpn)
        if m2:
            val = _decode_eia3(m2.group(1))
            if val is not None:
                return Decoded(val * 1e-12, "C", TOL_LETTER_PCT.get(m2.group(2).upper()), "Murata/Kemet 3-digit+tol")

    return None


# ---------------------------------------------------------------------------
# Allowlist -- hand-curated only. No writer/generator function exists in
# this module on purpose (see module docstring).
# ---------------------------------------------------------------------------


@dataclass
class AllowlistEntry:
    file: str
    ref: str
    mpn: str
    checks: set[str]  # subset of {"eseries", "decode"}
    reason: str


def load_allowlist(path: Path) -> list[AllowlistEntry] | None:
    """Load the hand-curated allowlist. Returns None on any parse failure
    (caller must treat that as a tool error, not an empty-but-valid list)."""
    if not path.is_file():
        return []
    import yaml

    try:
        data = yaml.safe_load(path.read_text())
    except Exception:
        return None
    if data is None:
        return []
    if not isinstance(data, dict) or "allowlist" not in data:
        return None
    entries_raw = data["allowlist"]
    if not isinstance(entries_raw, list):
        return None
    entries: list[AllowlistEntry] = []
    for e in entries_raw:
        if not isinstance(e, dict):
            return None
        required = ("file", "ref", "mpn", "checks", "reason")
        if not all(k in e for k in required):
            return None
        checks = e["checks"]
        if isinstance(checks, str):
            checks = [checks]
        if not isinstance(checks, list) or not all(c in ("eseries", "decode") for c in checks):
            return None
        if not isinstance(e["reason"], str) or not e["reason"].strip():
            return None
        entries.append(
            AllowlistEntry(file=e["file"], ref=e["ref"], mpn=e["mpn"], checks=set(checks), reason=e["reason"])
        )
    return entries


def allowlist_covers(entries: list[AllowlistEntry], part: ParsedPart, check: str) -> AllowlistEntry | None:
    for e in entries:
        if e.file == part.file and e.ref == part.ref and e.mpn == part.mpn and check in e.checks:
            return e
    return None


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    part: ParsedPart
    kind: str  # "eseries" or "decode"
    detail: str
    allowlisted: bool
    allow_reason: str = ""


@dataclass
class Analysis:
    parts: list[ParsedPart]
    decoded_count: int
    unchecked_count: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def new_violations(self) -> list[Finding]:
        return [f for f in self.findings if not f.allowlisted]

    @property
    def allowlisted_findings(self) -> list[Finding]:
        return [f for f in self.findings if f.allowlisted]


def analyze(parts: list[ParsedPart], allowlist: list[AllowlistEntry]) -> Analysis:
    decoded_count = 0
    unchecked_count = 0
    findings: list[Finding] = []

    for part in parts:
        decoded = decode_mpn(part.mpn)

        # --- MPN value-decode agreement ---
        if decoded is None:
            unchecked_count += 1
        else:
            decoded_count += 1
            if decoded.kind == part.kind and part.declared_value:
                ratio = decoded.value / part.declared_value
                agrees = abs(ratio - 1) < 0.02
            else:
                agrees = False
            if not agrees:
                entry = allowlist_covers(allowlist, part, "decode")
                findings.append(
                    Finding(
                        part=part,
                        kind="decode",
                        detail=(
                            f"MPN {part.mpn!r} ({decoded.family}) encodes "
                            f"{_fmt(decoded.value, part.kind)}, but the declared value is "
                            f"{_fmt(part.declared_value, part.kind)}"
                        ),
                        allowlisted=entry is not None,
                        allow_reason=entry.reason if entry else "",
                    )
                )

        # --- E-series membership ---
        eff_tol = part.declared_tol_pct
        if eff_tol is None and decoded is not None:
            eff_tol = decoded.tol_pct
        series_name = series_for_tolerance(eff_tol)
        if series_name is not None:
            ok = in_series(part.declared_value, series_name)
            required_desc = series_name
        else:
            ok = any(in_series(part.declared_value, s) for s in ALL_SERIES_NAMES)
            required_desc = "any standard series (tolerance unspecified)"

        if not ok:
            neighbor_series = series_name or "E96"
            neighbors = nearest_in_series(part.declared_value, neighbor_series)
            entry = allowlist_covers(allowlist, part, "eseries")
            findings.append(
                Finding(
                    part=part,
                    kind="eseries",
                    detail=(
                        f"{_fmt(part.declared_value, part.kind)} is not a member of "
                        f"{required_desc}; nearest legal neighbours "
                        f"({neighbor_series}): "
                        + ", ".join(_fmt(n, part.kind) for n in neighbors)
                    ),
                    allowlisted=entry is not None,
                    allow_reason=entry.reason if entry else "",
                )
            )

    return Analysis(parts=parts, decoded_count=decoded_count, unchecked_count=unchecked_count, findings=findings)


def _fmt(value: float, kind: str) -> str:
    if kind == "R":
        if value >= 1e6:
            return f"{value / 1e6:g}Mohm"
        if value >= 1e3:
            return f"{value / 1e3:g}kohm"
        return f"{value:g}ohm"
    # capacitor, base unit farads
    if value >= 1e-6:
        return f"{value * 1e6:g}uF"
    if value >= 1e-9:
        return f"{value * 1e9:g}nF"
    return f"{value * 1e12:g}pF"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fabricated-MPN / non-standard-value CI gate")
    parser.add_argument("--ato-glob", default=DEFAULT_ATO_GLOB, help="Glob (relative to repo root) for .ato sources")
    parser.add_argument(
        "--allowlist",
        default=str(REPO_ROOT / DEFAULT_ALLOWLIST),
        help="Path to the hand-curated allowlist YAML",
    )
    args = parser.parse_args()

    ato_files = sorted(REPO_ROOT.glob(args.ato_glob))
    if not ato_files:
        print(
            f"[MPN-GATE-ERROR] No .ato files matched glob {args.ato_glob!r} under {REPO_ROOT}. "
            "This is a tool error, not a clean design -- never treated as 0 violations.",
            file=sys.stderr,
        )
        sys.exit(5)

    parts = parse_all(args.ato_glob, REPO_ROOT)
    if not parts:
        print(
            "[MPN-GATE-ERROR] 0 resistor/capacitor value+mpn pairs parsed from "
            f"{len(ato_files)} .ato file(s). Either the design has no passives (implausible "
            "for this project) or the parser has drifted from the source syntax -- either way "
            "this is a tool error, never a pass. See parse_ato_file()'s VALUE_RE/MPN_RE.",
            file=sys.stderr,
        )
        sys.exit(5)

    allowlist_path = Path(args.allowlist)
    allowlist = load_allowlist(allowlist_path)
    if allowlist is None:
        print(
            f"[MPN-GATE-ERROR] Allowlist at {allowlist_path} exists but could not be parsed "
            "(bad YAML or missing required fields: file/ref/mpn/checks/reason on some entry). "
            "Failing closed rather than silently treating it as empty.",
            file=sys.stderr,
        )
        sys.exit(5)

    result = analyze(parts, allowlist)

    print(f"Parts inspected: {len(result.parts)}  (from {len(ato_files)} .ato file(s))")
    print(f"Values checked (E-series membership): {len(result.parts)}")
    print(f"MPNs decoded (known manufacturer-prefix family): {result.decoded_count}")
    print(f"MPNs unchecked (unrecognised prefix -- reported, not silently passed): {result.unchecked_count}")
    print(f"Allowlist entries loaded: {len(allowlist)}")

    new_violations = result.new_violations
    allowlisted = result.allowlisted_findings

    if allowlisted:
        print(f"\n=== ALLOWLISTED (suppressed, {len(allowlisted)}) ===")
        for f in allowlisted:
            print(f"  {f.part.file}:{f.part.line} {f.part.ref} ({f.part.mpn}) [{f.kind}] -- {f.allow_reason}")

    exit_code = 0
    gh_summary_path = get_github_summary_path()
    gh_summary = open(gh_summary_path, "a") if gh_summary_path else None

    if new_violations:
        print(f"\n=== NEW VIOLATIONS ({len(new_violations)}) ===")
        for f in new_violations:
            print(f"\n  {f.part.file}:{f.part.line}  {f.part.ref}  mpn={f.part.mpn!r}  [{f.kind}]")
            print(f"    {f.detail}")
            print(
                "    Remediation: verify against a real distributor/manufacturer page, then "
                "either fix the value/MPN in elec/src, or add a justified entry to "
                f"{allowlist_path.name} (hand-edited only -- see module docstring)."
            )
        exit_code = 3
        if gh_summary:
            gh_summary.write(f"### MPN Fabrication Gate -- {len(new_violations)} NEW VIOLATION(S)\n")
            for f in new_violations:
                gh_summary.write(f"- `{f.part.file}:{f.part.line}` `{f.part.ref}` (`{f.part.mpn}`): {f.detail}\n")
    else:
        print("\nMPN fabrication gate PASSED -- 0 new violations")
        if gh_summary:
            gh_summary.write("### MPN Fabrication Gate -- PASSED (0 new violations)\n")

    if gh_summary:
        gh_summary.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
