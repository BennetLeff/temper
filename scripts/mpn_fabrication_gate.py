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
     is recognised, the value the MPN itself encodes must agree with the
     declared value within 2%. Unrecognised prefixes are counted and reported
     as UNCHECKED -- never silently treated as passing. The recognised
     families, each transcribed from that manufacturer's published
     part-numbering / ordering-information table (cited by document number and
     URL in the decoder's own docstring, never inferred from an MPN already in
     this repo), are: Yageo RC/RSF, Vishay CRCW/CRGP, Panasonic ERA-xAEB,
     Murata/Kemet 3-digit-EIA-coded MLCCs, Vishay AC/AC-AT/AC-NI cemented
     wirewound, TDK/EPCOS B32xxx/B81xxx film and EMI-suppression capacitors,
     Murata BLM/BLA chip ferrite beads, Nippon Chemi-Con 18-field aluminium
     electrolytic/polymer capacitors, WIMA FKP 1 pulse capacitors, Yageo RT
     thin-film resistors, Vishay VY1 ceramic disc safety capacitors and
     Vishay WSLP Power Metal Strip shunts.

WHAT CHECK 2 IS NOT: it is a *consistency* check, not an *existence* check.
A well-formed MPN for a part that no manufacturer ever built will decode
cleanly and agree with its declared value. Two of the five fabrications in the
2026-07-27 audit have exactly that shape --

  * ``EKZE251ELL332MM40S`` decodes under the published Chemi-Con 18-field
    scheme to 3300 uF, which is what it was declared as; it was caught because
    it existed at no distributor, not because it decoded wrong.
  * ``DE1E3KX222MA4BA01`` decodes under Murata's published DE scheme to
    2200 pF, which is what it was declared as; it was caught because no Murata
    document pairs its ``A4B`` lead style with its ``A01`` individual-spec
    suffix -- a catalogue fact, not an encoding fact.

That is why the Murata DE family is deliberately NOT taught to this decoder
(see the note above FAMILIES): teaching it would move the one MPN we know to
be invented from the honest UNCHECKED column into the "decoded, agrees"
column. Distributor/catalogue existence still has to be established by a human
with a browser; this gate only ever proves internal consistency.

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
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root

REPO_ROOT = find_repo_root()

DEFAULT_ATO_GLOB = "elec/src/*.ato"
DEFAULT_ALLOWLIST = "mpn-fabrication-allowlist.yaml"

# Above this many UNCHECKED parts, the full per-part listing is replaced by
# per-family counts only (plus a hint to force it). 19 today is fine to
# always print in full; a few hundred would just be CI-log noise nobody
# reads. --full-unchecked-list overrides this cap on request.
UNCHECKED_LIST_CAP = 60

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


# ---------------------------------------------------------------------------
# Why capacitor/bead/shunt decoders return ``tol_pct=None``
#
# ``Decoded.tol_pct`` is not a report field. Its ONLY consumer is analyze(),
# where it is the fallback that picks which IEC 60063 E-series the *declared*
# value must belong to when the .ato line omits an explicit tolerance. That
# mapping (tolerance -> E6/E12/E24/E48/E96/E192) is a resistor convention, and
# pushing a decoded capacitor tolerance letter through it manufactures false
# violations:
#
#   c_bus1 = 1800 uF, MPN EKMQ251VSN182MA50S, field-14 tolerance code M = +/-20%.
#   Feeding 20% into series_for_tolerance() demands E6 membership, and 1.8 is
#   not an E6 mantissa -- yet 1800 uF/250 V is a catalogued Chemi-Con KMQ part.
#   Aluminium electrolytics are simply not selected off the E6 grid the way a
#   +/-20% resistor is.
#
# So: resistor families (Vishay AC -- whose datasheet explicitly says
# "Resistance value to be selected from E24 series" -- and Yageo RT thin film)
# return their decoded tolerance, because for them the tolerance -> series
# mapping is the right concept. Capacitor families (TDK film, Chemi-Con
# electrolytic, WIMA film, Vishay VY1 ceramic disc), the ferrite bead
# (impedance at 100 MHz, not a resistance) and the current-sense shunt (whose
# catalogue values 0.0005/0.001/0.002/0.005/0.01 ohm are not an E-series) all
# return None. Their tolerance letter is still *parsed* -- a string whose
# tolerance field is not a published code fails to match at all and stays
# UNCHECKED -- it is just not used to impose a resistor's series rule.
# ---------------------------------------------------------------------------


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


def _decode_sig_r(code: str) -> float | None:
    """Decode a fixed-width code where a letter marks the decimal point and
    an all-digit code means "first digits significant, last digit = number of
    trailing zeros". Used for the Nippon Chemi-Con 18-field capacitance and
    rated-voltage fields, whose rule is stated verbatim in the part-numbering
    system document: "The first two digits are significant figures ... and the
    third digit ... indicates the number of zeros ... R indicates the decimal
    point for capacitance less than 10uF (e.g. 1R0 = 1.0uF; 100 = 10uF;
    101 = 100uF; 102 = 1,000uF; 103 = 10,000uF)"."""
    if "R" in code:
        try:
            return float(code.replace("R", ".", 1))
        except ValueError:
            return None
    return _decode_eia3(code)


# --- Family registry -------------------------------------------------------
#
# Each entry is (name, compiled shape regex, decode(match) -> Decoded | None,
# value-segment description used in the UNCHECKED reason line). decode_mpn()
# and classify_unchecked() both walk this one list, so a shape that matches a
# family but whose *value* segment does not parse is reported as that family's
# UNCHECKED -- it can never be silently dropped, and the two functions cannot
# drift apart.
#
# EVERY encoding below is transcribed from the manufacturer's own published
# part-numbering / ordering-information table, cited by document number and URL
# at the family. None of them was inferred from an MPN already present in this
# repository: inferring a scheme from a string you are about to validate makes
# that string valid by construction, which is exactly how a fabricated MPN gets
# promoted from "honestly unchecked" to "falsely verified".
#
# Deliberately NOT implemented, and why:
#
#   * Murata DE / safety-standard-certified disc caps (DE1E/DE2E/DEJ). The
#     published scheme (Murata Cat.No.C85E-2, "Part Numbering", p.2) exists and
#     is unambiguous -- but running the known fabrication DE1E3KX222MA4BA01
#     through it yields a *fully well-formed* part: DE / 1 = IEC 60384-14 Class
#     X1,Y1 / E3 temperature characteristic / KX rated-voltage+certified type /
#     222 = 2200 pF / M = +/-20% / A4 = vertical crimp long, 10 mm lead spacing
#     / B = bulk / A01 = individual specification code (the document explicitly
#     allows a trailing three-digit alphanumeric individual-spec code). Its
#     declared value, 2.2 nF, agrees. That fabrication was caught by catalogue
#     absence -- the A4B lead style pairs with N01F and the A01 suffix pairs
#     with A5B, and no Murata document lists A4B+A01 -- which is a *catalogue*
#     fact, not an *encoding* fact, and therefore not knowable offline. A DE
#     decoder here would return "decodes to 2200 pF, agrees" and quietly move
#     the one MPN we know to be invented out of the UNCHECKED column. Leaving
#     DE unimplemented is the correct outcome.
#   * Vishay VY2 ceramic disc. Same ordering-code layout as VY1 but a different
#     size/voltage code set in a different document (28535) that was not read;
#     only the VY1 document (28537) was verified, so only VY1 is decoded.
#   * Nippon Chemi-Con categories K (MLCC), F (film), D (EDLC), T (varistor),
#     L (choke). The 18-field skeleton is shared, but the document only shows
#     the capacitance-field unit convention for the aluminium/polymer capacitor
#     product-code guides, so only categories A/H/E/B are decoded.

RT_TOL_LETTER_PCT = {
    # Yageo RT ordering-information field (2) TOLERANCE. Distinct from
    # TOL_LETTER_PCT: L/P/W have no meaning in the generic table, and reusing
    # the generic table would silently mis-read them.
    "L": 0.01, "P": 0.02, "W": 0.05, "B": 0.1, "C": 0.25, "D": 0.5, "F": 1.0,
}

# WIMA FKP 1 rated-voltage letter, read off the eight "General Data" table
# headers in the FKP 1 datasheet (each column's part numbers all carry that
# column's letter): G/J/O/R/T/U/X/Y.
WIMA_FKP1_VOLTAGE = {
    "G": "400 VDC", "J": "630 VDC", "O": "1000 VDC", "R": "1250 VDC",
    "T": "1600 VDC", "U": "2000 VDC", "X": "4000 VDC", "Y": "6000 VDC",
}

# Vishay AC/AC-AT/AC-NI resistance multiplier digit (the 4th digit of the
# 4-digit VALUE field). Note the negative powers -- "1509" is 15 ohm, not
# 150 x 10^9 -- which is why this family cannot be guessed.
VISHAY_AC_MULTIPLIER = {"7": -3, "8": -2, "9": -1, "0": 0, "1": 1, "2": 2}


def _dec_yageo_rc(m: re.Match) -> Decoded | None:
    val = _decode_rkm(m.group(4))
    return None if val is None else Decoded(val, "R", TOL_LETTER_PCT.get(m.group(2).upper()), "Yageo RC")


def _dec_yageo_rsf(m: re.Match) -> Decoded | None:
    val = _decode_rkm(m.group(2))
    return None if val is None else Decoded(val, "R", TOL_LETTER_PCT.get(m.group(1).upper()), "Yageo RSF")


def _dec_vishay_crcw(m: re.Match) -> Decoded | None:
    val = _decode_rkm(m.group(2))
    return None if val is None else Decoded(val, "R", TOL_LETTER_PCT.get(m.group(3).upper()), "Vishay CRCW")


def _dec_vishay_crgp(m: re.Match) -> Decoded | None:
    val = _decode_rkm(m.group(3))
    return None if val is None else Decoded(val, "R", TOL_LETTER_PCT.get(m.group(2).upper()), "Vishay CRGP")


def _dec_panasonic_era(m: re.Match) -> Decoded | None:
    val = _decode_eia3(m.group(2))
    # AEB is Panasonic's 0.1%-tolerance ERA sub-designation.
    return None if val is None else Decoded(val, "R", 0.1, "Panasonic ERA-xAEB")


def _dec_mlcc_3digit(m: re.Match) -> Decoded | None:
    m2 = re.search(r"(\d{3})([KJMZ])", m.group(0))
    if not m2:
        return None
    val = _decode_eia3(m2.group(1))
    if val is None:
        return None
    return Decoded(val * 1e-12, "C", TOL_LETTER_PCT.get(m2.group(2).upper()), "Murata/Kemet 3-digit+tol")


def _dec_vishay_ac(m: re.Match) -> Decoded | None:
    """Vishay Draloric AC / AC-AT / AC-NI cemented axial wirewound.

    Source: Vishay document number 28730, "AC, AC-AT, AC-NI ... Cemented Axial
    Leaded, WSZ (SMD) Wirewound Resistors", rev. 05-Dec-2024, page 2, table
    "PART NUMBER AND PRODUCT DESCRIPTION" (worked examples AC03000001509JAC00 /
    AC03AT0001509JAC00 / AC03NI0001008JAC00).
    https://www.vishay.com/docs/28730/ac_ac-at_ac-ni.pdf

    Fields, in the datasheet's own order:
      MODEL (7)      AC01000/AC03000/AC04000/AC05000/AC07000/AC10000 and the
                     ...AT0 (AEC-Q200) / ...NI0 (non-inductive) variants.
      VARIANT (1)    lead form (0 neutral, 1 RT, 2 SWI, 3..Q kink/pitch codes).
      TCR/MATERIAL   "0 = standard" is the only published code.
      VALUE (4)      3-digit value + 1-digit multiplier, multipliers
                     7=x10^-3 8=x10^-2 9=x10^-1 0=x10^0 1=x10^1 2=x10^2.
      TOLERANCE (1)  J = +/- 5 % (the only tolerance in the standard table).
      PACKAGING (2)  AC/A1/AB/AE/AQ/R1/LB/LC/LA/BM/BW/RC/GC.
      SPECIAL (2)    "00 = standard", 2-digit code = customized version.

    DECODED: model, value+multiplier, tolerance. DELIBERATELY IGNORED: variant
    (lead form), TCR/material digit, packaging code, special code -- none of
    them constrains the electrical value, and pretending to check them would be
    asserting more than the table supports.

    Page 1 note (1) of the same document -- "Resistance value to be selected
    from E24 series" -- is why this family returns its tolerance: the E-series
    check downstream is the manufacturer's own stated constraint here."""
    mult = VISHAY_AC_MULTIPLIER.get(m.group("mult"))
    tol = TOL_LETTER_PCT.get(m.group("tol"))
    if mult is None or tol is None:
        return None
    return Decoded(float(m.group("sig")) * (10**mult), "R", tol, f"Vishay AC{m.group('model')} wirewound")


def _dec_tdk_film(m: re.Match) -> Decoded | None:
    """TDK Electronics (EPCOS) B32xxx / B81xxx film and EMI-suppression caps.

    Source: TDK Electronics, "Film Capacitors -- Marking and ordering code
    system", July 2020, section 2 "Ordering code system", page 7.
    https://www.tdk-electronics.tdk.com/download/530780/f88694d2625ccc91ea99f82a4261b9f9/pdf-markingandorderingcodesystem.pdf

    Verbatim digit table:
      1        B = Passive components
      2, 3     32 = Metallized film capacitors, EMI suppression capacitors
               81 = EMI suppression capacitors
      4 ... 6  Type (block 1 is termed the "type number")
      7        Revision status
      8        Rated DC voltage, coded (not for EMI suppression capacitors)
      9 ... 11 Rated capacitance (coding method for value in pF)
               Example: B 3 2 6 5 2 A 3 [1 5 4] K = 15 x 10^4 pF = 150 nF
      12       Code letter for capacitance tolerance
      13 ... 15 Codes for lead and taping parameters
      16 ... 18 Internal use
    Tolerance letters (same document, page 5): A = no code defined,
      H = +/-2.5 %, J = +/-5 %, K = +/-10 %, M = +/-20 %.

    DECODED: block 1 (type number), digits 9-11 capacitance, digit 12
    tolerance. DELIBERATELY IGNORED: digit 7 revision status, digit 8 rated DC
    voltage (the document says "coded" but publishes no code table, and it is
    explicitly meaningless for EMI-suppression types such as B32922), and
    digits 13-15 lead/taping parameters."""
    val = _decode_eia3(m.group("cap"))
    if val is None:
        return None
    return Decoded(val * 1e-12, "C", None, f"TDK/EPCOS B{m.group('fam')}{m.group('type')} film")


def _dec_murata_blm(m: re.Match) -> Decoded | None:
    """Murata BLM/BLA chip ferrite beads.

    Source: Murata, "Part Numbering -- Chip Ferrite Beads", worked example
    BL|M|18|AG|102|S|N|1|D.
    https://media.digikey.com/pdf/Data%20Sheets/Murata%20PDFs/BLM,%20BLA%20Part%20Numbering%20Guide.pdf

    Fields: (1) Product ID BL; (2) Type A = array, M = monolithic;
    (3) Dimensions LxW 03/15/18/2A/21/31/41 (0201..1806); (4) Characteristics /
    applications (AF, AG, AJ, AH, BA, BB, BD, BE, PF, PG, RK, HG, EG, HB, HD,
    HK, GG); (5) Impedance -- verbatim: "Expressed by three figures. The unit
    is in ohm. The first and second figures are significant digits, and the
    third figure expresses the number of zeros which follow the two figures";
    (6) Performance (S = Sn plating); (7) Category (N = standard type);
    (8) Number of circuits (1 or 4); (9) Packaging.

    DECODED: product ID, type, dimension code, impedance. DELIBERATELY
    IGNORED: characteristics code, performance, category, circuit count,
    packaging.

    NOTE ON UNITS: field (5) is the *impedance at 100 MHz*, not a DC
    resistance, and a bead's impedance tolerance (typically +/-25 %) says
    nothing about IEC 60063 membership -- hence tol_pct=None. The value is
    still comparable against the declared one because this design models the
    bead as a Resistor whose value is its 100 MHz impedance (see the inline
    "Target: ~120ohm @ 100MHz" comment at the declaration site)."""
    val = _decode_eia3(m.group("imp"))
    if val is None:
        return None
    return Decoded(val, "R", None, f"Murata BL{m.group('type')}{m.group('dim')} ferrite bead")


def _dec_chemicon(m: re.Match) -> Decoded | None:
    """Nippon Chemi-Con / United Chemi-Con aluminium electrolytic and polymer
    capacitors (18-field global part number).

    Source: Nippon Chemi-Con, "PART NUMBERING SYSTEM", CAT.No.E1001U --
    "Categories" table (page 1) and the "Product code guide (Snap-in type)"
    (page 6, worked example EKMS401VSN331MR30S) plus the identically-fielded
    radial/SMD/screw guides (pages 2-5, 7).
    https://chemi-con.com/wp-content/uploads/2021/04/Part-numbering-system.pdf

    Field layout, identical across every form factor in that document:
      1        Category: A polymer solid, H polymer hybrid, E aluminium
               electrolytic (polar), B aluminium electrolytic (bi-polar),
               K MLCC, F film, D EDLC, T varistor, L choke.
      2 ... 4  Series code (KMQ, KMS, KMH, PXJ, ...).
      5 ... 7  Voltage code.
      8 ... 10 Terminal / lead-forming / taping codes.
      11 ... 13 Capacitance code, in microfarads.
      14       Capacitance tolerance: M = +/-20 %, V = -10/+20 %.
      15 ... 17 Size code (diameter + length).
      18       Supplement code (sleeve / terminal plating material).
    The capacitance rule is stated verbatim on page 8 of the same document
    (U37F series, same 18-field system): "Expressed in Microfarads. The first
    two digits are significant figures ... and the third digit ... indicates
    the number of zeros ... R indicates the decimal point for capacitance less
    than 10uF (e.g. 1R0 = 1.0uF; 100 = 10uF; 101 = 100uF; 102 = 1,000uF;
    103 = 10,000uF)".

    DECODED: category, series, fields 11-13 capacitance, field 14 tolerance
    letter. DELIBERATELY IGNORED: voltage code, terminal/lead-forming/taping
    codes, size code, supplement code. (The voltage code follows the same
    significant-figures rule and could be checked, but ParsedPart carries no
    declared voltage, so checking it would be inventing a comparison.)"""
    val = _decode_sig_r(m.group("cap"))
    if val is None:
        return None
    return Decoded(val * 1e-6, "C", None, f"Chemi-Con {m.group('cat')}{m.group('series')} electrolytic")


def _dec_wima_fkp1(m: re.Match) -> Decoded | None:
    """WIMA FKP 1 polypropylene pulse capacitors.

    Source: WIMA, "FKP 1" datasheet pages 63-68 (rev. 03.26) --
    https://www.wima.de/wp-content/uploads/media/e_WIMA_FKP_1.pdf -- read as
    an ordering-information table: eight "General Data" tables, one per rated
    voltage (400/630/1000/1250/1600/2000/4000/6000 VDC), each listing
    (capacitance, W, H, L, PCM, part number) rows, plus the "Part number
    completion" box repeated on every page.

    The letter after "FKP1" is the rated voltage, fixed by which table the row
    lives in: G 400, J 630, O 1000, R 1250, T 1600, U 2000, X 4000, Y 6000 VDC.

    Capacitance: the manufacturer's rows give
      "...0[0]100 4"  = 100 pF     "...0[1]100 4" = 1000 pF
      "...0[2]100 4"  = 0.01 uF    "...0[3]100 5" = 0.1 uF
      "...0[4]100 7"  = 1.0 uF
    i.e. value_pF = <3 significant digits> x 10^<decade-group digit>, holding
    across all six mantissas (100/150/220/330/470/680), all five decade groups
    and all eight voltage tables. Worked checks against WIMA's own rows:
    FKP1T031507G = 150 x 10^3 pF = 0.15 uF at 1600 VDC (its listed capacitance);
    FKP1T021506B = 150 x 10^2 pF = 0.015 uF at 1600 VDC (ditto).

    Completion block, verbatim from the datasheet box: "Version code: 2-pin =
    00, 4-pin = D4; Tolerance: 20 % = M, 10 % = K, 5 % = J; Packing: bulk = S;
    Pin length: 6-2 = SD".

    DECODED: series, rated-voltage letter, decade group + 3 significant
    digits, version code, tolerance letter. DELIBERATELY IGNORED: the digit
    immediately after the voltage letter (a series/variant digit the datasheet
    never explains -- it is 0 in seven of the eight voltage tables and 1 in the
    1000 VDC table), the case-size digit and case letter, and the packing /
    pin-length codes beyond the version+tolerance pair."""
    val = _decode_eia3(m.group("sig") + m.group("group"))
    if val is None:
        return None
    voltage = WIMA_FKP1_VOLTAGE[m.group("volt")]
    return Decoded(val * 1e-12, "C", None, f"WIMA FKP1 ({m.group('volt')} = {voltage})")


def _dec_yageo_rt(m: re.Match) -> Decoded | None:
    """Yageo RT series thin-film chip resistors.

    Source: Yageo, "DATA SHEET -- THIN FILM CHIP RESISTORS, High precision -
    high stability, RT series", product specification 2019-07-02 V.11, page 2,
    "ORDERING INFORMATION -- GLOBAL PART NUMBER & 12NC".
    https://www.yageo.com/en/Product/Index/rchip/thin_film/rt

    Layout: RT | (1) SIZE | (2) TOLERANCE | (3) PACKAGING TYPE | (4) TCR |
    (5) TAPING REEL | (6) RESISTANCE VALUE | (7) DEFAULT CODE L.
      (2) L +/-0.01 %, P +/-0.02 %, W +/-0.05 %, B +/-0.1 %, C +/-0.25 %,
          D +/-0.5 %, F +/-1 %
      (3) R = paper/PE taping reel, K = embossed taping reel
      (4) A 5, B 10, C 15, D 25, E 50 ppm/degC
      (5) 07 / 10 / 13 inch reel, 7W = 7 inch high power
      (6) "There are 2~4 digits indicated the resistor value. Letter R/K/M is
          decimal point", with the published resistance code rule
          1R = 1 ohm, 1R5 = 1.5, 10R = 10, 100R = 100, 1K = 1000,
          9K76 = 9760, 1M = 1,000,000.
    Datasheet's own ordering example: a 56 ohm +/-0.5 % TC50 0603 in a 7-inch
    reel is RT0603DRE0756RL.

    DECODED: size, tolerance letter, resistance value. DELIBERATELY IGNORED:
    packaging type, TCR letter, taping-reel code, trailing default code."""
    val = _decode_rkm(m.group("val"))
    tol = RT_TOL_LETTER_PCT.get(m.group("tol"))
    if val is None or tol is None:
        return None
    return Decoded(val, "R", tol, f"Yageo RT{m.group('size')} thin film")


def _dec_vishay_vy1(m: re.Match) -> Decoded | None:
    """Vishay BCcomponents VY1 EMI-suppression ceramic disc safety capacitors.

    Source: Vishay document number 28537, "VY1 Series -- EMI Suppression
    Safety Capacitor, Ceramic Disc, Class X1, 760 VAC, Class Y1, 500 VAC",
    rev. 18-Aug-2025, page 3, table "ORDERING CODE" (worked example
    VY1|101|K|31|Y5S|Q|6|T|V|0), cross-checked against the page-2 "TECHNICAL
    DATA" part-number column.
    https://www.vishay.com/docs/28537/vy1series.pdf

    Fields: Series VY1 | Capacitance value (3-digit EIA pF code, e.g. the
    page-2 rows 10 pF -> 100, 100 pF -> 101, 2200 pF -> 222) | Tolerance code
    (+/-10 % = K, +/-20 % = M) | Size code | Temperature coefficient (U2J,
    Y5S, Y5U, Y5V) | Rated voltage (Q = X1/Y1 500 V AC) | Lead wire diameter |
    Packaging / lead length (3 = bulk, T = tape and reel, U = ammopack) |
    Lead style (L = straight, V = inline kinked) | Lead spacing (0 = 10.0 mm,
    X = 12.5 mm).

    DECODED: series, capacitance code, tolerance code, temperature
    coefficient, rated-voltage code. DELIBERATELY IGNORED: size code, lead
    wire diameter, packaging, lead style, lead spacing."""
    val = _decode_eia3(m.group("cap"))
    if val is None:
        return None
    return Decoded(val * 1e-12, "C", None, f"Vishay VY1 ceramic disc ({m.group('tc')})")


def _dec_vishay_wslp(m: re.Match) -> Decoded | None:
    """Vishay Dale WSLP Power Metal Strip current-sense resistors.

    Source: Vishay document number 30122, "WSLP -- Power Metal Strip
    Resistors, Very High Power (to 3 W), Low Value (Down to 0.0005 ohm),
    Surface-Mount", rev. 09-Sep-2024, page 1, table "GLOBAL PART NUMBER
    INFORMATION" (worked example WSLP1206R0100FEA).
    https://www.vishay.com/docs/30122/wslp.pdf

    Fields: GLOBAL MODEL (8) WSLP0603/0805/1206/2010/2512 | RESISTANCE VALUE
    (5) verbatim: 'L = mOhm, R = decimal, 4L000 = 0.004 Ohm, R0100 = 0.01 Ohm
    ... Use "L" for resistance values < 0.01 Ohm' | TOLERANCE CODE (1)
    D = +/-0.5 %, F = +/-1.0 %, G = +/-2.0 % | PACKAGING CODE (2) EA = lead
    (Pb)-free tape/reel | SPECIAL (up to 2).

    DECODED: model, 5-digit resistance value, tolerance code. DELIBERATELY
    IGNORED: packaging code and special code.

    tol_pct is None on purpose: the datasheet's own value list for these parts
    (0.0005 / 0.001 / 0.002 / 0.005 / 0.007 / 0.01 ohm) is a milliohm shunt
    ladder, not an IEC 60063 series, so the decoded tolerance must not be used
    to demand E-series membership of the declared value."""
    code = m.group("val")
    tol = TOL_LETTER_PCT.get(m.group("tol"))
    if tol is None:
        return None
    if "L" in code:
        try:
            val = float(code.replace("L", ".", 1)) * 1e-3
        except ValueError:
            return None
    elif "R" in code:
        try:
            val = float(code.replace("R", ".", 1))
        except ValueError:
            return None
    else:
        return None
    return Decoded(val, "R", None, f"Vishay WSLP{m.group('model')} shunt")


FAMILIES: list[tuple[str, re.Pattern[str], Callable[[re.Match[str]], Decoded | None], str]] = [
    (
        "Yageo RC",
        re.compile(r"^RC(\d{4})([A-Z])[A-Z]?-(\d{2})([0-9A-Za-z]+)L$"),
        _dec_yageo_rc,
        "value segment {4!r} did not parse as an R/K/M-coded number",
    ),
    (
        "Yageo RSF",
        re.compile(r"^RSF\d{3}([A-Z])[A-Z]-\d{2}-([0-9A-Za-z]+)$"),
        _dec_yageo_rsf,
        "value segment {2!r} did not parse as an R/K/M-coded number",
    ),
    (
        "Vishay CRCW",
        re.compile(r"^CRCW(\d{4})([0-9A-Za-z]+?)([FJGD])([A-Z]{2,3})$"),
        _dec_vishay_crcw,
        "value segment {2!r} did not parse as an R/K/M-coded number",
    ),
    (
        "Vishay CRGP",
        re.compile(r"^CRGP(\d{4})([FJGD])([0-9A-Za-z]+)$"),
        _dec_vishay_crgp,
        "value segment {3!r} did not parse as an R/K/M-coded number",
    ),
    (
        "Panasonic ERA-xAEB",
        re.compile(r"^ERA-(\d)AEB(\d{3,4})V$"),
        _dec_panasonic_era,
        "value segment {2!r} did not parse as an EIA 3-digit code",
    ),
    (
        "Murata/Kemet 3-digit+tol",
        re.compile(r"^(?:(?:GRM|GCM)\d|C\d{4}C).*$"),
        _dec_mlcc_3digit,
        "no <3-digit><tolerance-letter> EIA code segment was found in it",
    ),
    # --- families added by feat/mpn-decoder-families; see each decoder's
    # docstring for the manufacturer document the shape comes from.
    (
        "Vishay AC wirewound",
        re.compile(
            r"^AC(?P<model>\d{2})(?:000|AT0|NI0)(?P<variant>[0-9A-Z])(?P<tcr>0)"
            r"(?P<sig>\d{3})(?P<mult>\d)(?P<tol>[A-Z])(?P<pkg>[A-Z0-9]{2})(?P<special>[A-Z0-9]{2})$"
        ),
        _dec_vishay_ac,
        "VALUE segment {sig!r}+{mult!r} / tolerance {tol!r} is not a published "
        "3-digit-value + multiplier(7,8,9,0,1,2) + tolerance-letter combination",
    ),
    (
        "TDK/EPCOS B32/B81 film",
        re.compile(
            r"^B(?P<fam>32|81)(?P<type>\d{3})(?P<rev>[A-Z])(?P<volt>[0-9A-Z])"
            r"(?P<cap>\d{3})(?P<tol>[AHJKM])(?P<lead>[0-9A-Z]{3})$"
        ),
        _dec_tdk_film,
        "digits 9-11 {cap!r} did not parse as a pF-coded rated capacitance",
    ),
    (
        "Murata BLM/BLA ferrite bead",
        re.compile(
            r"^BL(?P<type>[AM])(?P<dim>03|15|18|2A|21|31|41)(?P<char>[A-Z]{2})"
            r"(?P<imp>\d{3})(?P<perf>[A-Z])(?P<cat>[A-Z])(?P<circuits>[14])(?P<pkg>[A-Z])$"
        ),
        _dec_murata_blm,
        "impedance segment {imp!r} did not parse as a 3-figure ohm code",
    ),
    (
        "Chemi-Con 18-field electrolytic",
        re.compile(
            r"^(?P<cat>[ABEH])(?P<series>[A-Z0-9]{3})(?P<volt>[0-9R]{3})"
            r"(?P<term>[A-Z0-9]{3})(?P<cap>[0-9R]{3})(?P<tol>[MV])"
            r"(?P<size>[A-Z0-9]{3})(?P<supp>[A-Z0-9])$"
        ),
        _dec_chemicon,
        "fields 11-13 {cap!r} did not parse as a microfarad capacitance code",
    ),
    (
        "WIMA FKP1",
        re.compile(
            r"^FKP1(?P<volt>[GJORTUXY])(?P<variant>\d)(?P<group>[0-4])(?P<sig>\d{3})"
            r"(?P<size>\d)(?P<case>[A-Z])(?P<version>00|D4)(?P<tol>[MKJ])(?P<rest>[A-Z0-9]{3})$"
        ),
        _dec_wima_fkp1,
        "decade-group digit {group!r} + significant figures {sig!r} did not parse",
    ),
    (
        "Yageo RT thin film",
        re.compile(
            r"^RT(?P<size>\d{4})(?P<tol>[A-Z])(?P<pkg>[RK])(?P<tcr>[A-E])"
            r"(?P<reel>07|10|13|7W)(?P<val>[0-9RKM]{2,5})L$"
        ),
        _dec_yageo_rt,
        "value segment {val!r} / tolerance {tol!r} is not a published "
        "R/K/M-coded value + tolerance-letter (L/P/W/B/C/D/F) combination",
    ),
    (
        "Vishay VY1 ceramic disc",
        re.compile(
            r"^VY1(?P<cap>\d{3})(?P<tol>[KM])(?P<size>\d{2})(?P<tc>U2J|Y5S|Y5U|Y5V)"
            r"(?P<volt>[A-Z])(?P<leaddia>\d)(?P<pkg>[3TU])(?P<leadstyle>[LV])(?P<spacing>[0X])$"
        ),
        _dec_vishay_vy1,
        "capacitance segment {cap!r} did not parse as a 3-digit EIA pF code",
    ),
    (
        "Vishay WSLP shunt",
        re.compile(
            r"^WSLP(?P<model>0603|0805|1206|2010|2512)(?P<val>[0-9RL]{5})"
            r"(?P<tol>[DFG])(?P<pkg>[A-Z]{2})(?P<special>[A-Z0-9]{0,2})$"
        ),
        _dec_vishay_wslp,
        "resistance segment {val!r} is not a published L-(milliohm) or "
        "R-(decimal) coded 5-character value",
    ),
]

KNOWN_FAMILY_NAMES = ", ".join(name for name, _, _, _ in FAMILIES)


def decode_mpn(mpn: str) -> Decoded | None:
    """Return the value+kind the MPN itself encodes, or None if the
    manufacturer-prefix family isn't recognised (UNCHECKED, not a pass)."""
    for _name, pattern, decode, _fail in FAMILIES:
        m = pattern.match(mpn)
        if m:
            decoded = decode(m)
            if decoded is not None:
                return decoded
    return None


def _guess_prefix(mpn: str) -> str:
    """Best-effort manufacturer-prefix guess for grouping UNCHECKED MPNs --
    the leading run of letters (e.g. "EKMQ251VSN182MA50S" -> "EKMQ",
    "DE1E3KX222MA4BA01" -> "DE"). Used only for report grouping, never for
    decoding: an MPN that reaches this function has already failed every
    real decoder pattern in decode_mpn()."""
    m = re.match(r"^[A-Za-z]+", mpn)
    return m.group(0) if m else mpn[:4]


def classify_unchecked(mpn: str) -> tuple[str, str]:
    """For an MPN that decode_mpn() returned None for, explain *why* --
    distinguishing "shape matched a known family but the value segment
    itself didn't parse" (a decoder bug worth fixing) from "no known
    family's shape matched at all" (an MPN the decoder has never been
    taught). Returns (group, reason); group is used to bucket the report by
    manufacturer-prefix family per the task's design call -- that's
    usually the more actionable axis than source file, since the fix is
    normally "teach the decoder this family."

    This walks the same FAMILIES registry decode_mpn() does, so the two can
    no longer drift apart: a shape that matches family F but whose value
    segment does not parse is reported under F, with F's own description of
    what failed."""
    for name, pattern, _decode, fail_template in FAMILIES:
        m = pattern.match(mpn)
        if m:
            # Templates reference either 1-based positional groups ("{4!r}",
            # the pre-existing families) or named groups ("{cap!r}", the
            # families added later). Pad index 0 so "{4}" means group 4.
            args = ("",) + tuple(g if g is not None else "" for g in m.groups())
            kwargs = {k: (v if v is not None else "") for k, v in m.groupdict().items()}
            try:
                detail = fail_template.format(*args, **kwargs)
            except (KeyError, IndexError):
                detail = fail_template
            return name, f"matches {name} part-number shape, but {detail}"

    prefix = _guess_prefix(mpn)
    return (
        prefix,
        f"unrecognised manufacturer-prefix family (leading prefix {prefix!r} is not one of the "
        f"decoder's known families: {KNOWN_FAMILY_NAMES})",
    )


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
        # `required` is a fixed 5-element literal written directly above --
        # never built from runtime/config data -- so it can never be empty
        # here; asserted rather than assumed so a future edit that turns
        # it into a computed/config-driven set is forced to reconsider
        # this guard.
        required = ("file", "ref", "mpn", "checks", "reason")
        assert required
        if not all(k in e for k in required):
            return None
        checks = e["checks"]
        if isinstance(checks, str):
            checks = [checks]
        if not isinstance(checks, list):
            return None
        if not checks:
            # An empty `checks` list is not "valid but covers nothing" --
            # allowlist_covers() would never match it (checking
            # `check in e.checks` against an empty set is always False),
            # so it would silently sit in the file as dead, un-auditable
            # weight. Before this guard, `not all(... for c in checks)`
            # was vacuously False for checks=[], so this branch never
            # rejected an empty list -- reject it explicitly instead.
            return None
        if not all(c in ("eseries", "decode") for c in checks):
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
class UncheckedPart:
    """One MPN whose manufacturer-prefix family decode_mpn() didn't
    recognise -- reported, never silently passed. See classify_unchecked()."""

    part: ParsedPart
    group: str
    reason: str


@dataclass
class Analysis:
    parts: list[ParsedPart]
    decoded_count: int
    unchecked_count: int
    findings: list[Finding] = field(default_factory=list)
    unchecked: list[UncheckedPart] = field(default_factory=list)

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
    unchecked: list[UncheckedPart] = []

    for part in parts:
        decoded = decode_mpn(part.mpn)

        # --- MPN value-decode agreement ---
        if decoded is None:
            unchecked_count += 1
            group, reason = classify_unchecked(part.mpn)
            unchecked.append(UncheckedPart(part=part, group=group, reason=reason))
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

    return Analysis(
        parts=parts,
        decoded_count=decoded_count,
        unchecked_count=unchecked_count,
        findings=findings,
        unchecked=unchecked,
    )


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
    parser.add_argument(
        "--full-unchecked-list",
        action="store_true",
        help=(
            "Force the full per-part UNCHECKED listing even past the "
            f"{UNCHECKED_LIST_CAP}-part summary cap (default: print per-family "
            "counts only above the cap)."
        ),
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

    if result.unchecked:
        print(f"\n=== MPN UNCHECKED, BY MANUFACTURER-PREFIX FAMILY ({len(result.unchecked)}) ===")
        groups: dict[str, list[UncheckedPart]] = defaultdict(list)
        for u in result.unchecked:
            groups[u.group].append(u)
        listing_full = len(result.unchecked) <= UNCHECKED_LIST_CAP or args.full_unchecked_list
        for group_name in sorted(groups):
            items = sorted(groups[group_name], key=lambda u: (u.part.file, u.part.line))
            print(f"  -- {group_name} ({len(items)}) --")
            if listing_full:
                for u in items:
                    print(f"    {u.part.file}:{u.part.line}  {u.part.ref}  mpn={u.part.mpn!r}")
                    print(f"      {u.reason}")
        if not listing_full:
            print(
                f"  {len(result.unchecked)} unchecked parts exceed the {UNCHECKED_LIST_CAP}-part "
                "detail cap -- per-family counts shown above. Re-run with --full-unchecked-list "
                "to print every ref/MPN/reason."
            )

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
