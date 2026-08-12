#!/usr/bin/env python3
"""HV netclass coverage gate: every mains/HV net has a netclass, and every
declared netclass actually enforces something.

Motivating defect (confirmed on ``origin/main``, 2026-07-29 -- fixed on the
``fix/recover-stranded-netclass-safety`` branch this gate is designed
against):

  1. ``+170V_BUS``, the live 170V DC bus (declared under
     ``elec/domain_manifest.yaml``'s ``HV`` domain), resolved to NO
     netclass at all via ``TEMPER_NET_ASSIGNMENTS``
     (``packages/temper-placer/src/temper_placer/core/design_rules.py``).
     ``DesignRules.get_rules_for_net`` falls through to a default,
     low-voltage clearance/creepage figure for any net with no matching
     override, net-class assignment, or name-pattern match -- so this
     silently downgraded a live 170V DC rail to LV separation for every
     Python-side (CP-SAT placer, router_v6) decision.
  2. ``+15V_LS`` (the low-side gate-driver rail, referenced to
     ``DC_BUS_RTN`` -- floats within the HV domain per the manifest) was
     assigned the low-voltage ``Power`` class instead of ``HighVoltage``.
  3. ``HighVoltageIsolated`` -- the gate-drive floating bootstrap-supply
     netclass -- is a real, intentional netclass (declared with a
     safety-relevant clearance figure and description in
     ``pcb/temper.kicad_pro``'s ``net_settings.classes``, and in
     ``TEMPER_NET_CLASSES`` once added), but
     ``scripts/generate_kicad_dru.py`` emitted ZERO rules referencing it
     by name -- a class that exists and enforces nothing. Any net ever
     assigned this class inherited only KiCad's per-netclass baseline
     clearance and no creepage protection at all.

Two independent properties are checked. They are kept separate because
they are different failure shapes -- fixing one does not imply the other
is fixed, and each needs its own falsifier:

PROPERTY 1 -- HV net coverage
------------------------------
Every net ``elec/domain_manifest.yaml`` declares under its ``HV`` domain
(the hand-reviewed, human-curated SSOT for which nets are mains/HV-domain,
also relied on by ``scripts/check_domain_partition.py``) must have an
entry in ``TEMPER_NET_ASSIGNMENTS``. A manifest-HV net absent from that
table silently falls through to ``DesignRules``' LV default for any
Python-side clearance/routing decision -- see the ``+170V_BUS`` defect
above.

Scope boundary, deliberately: this property checks *presence* of an
assignment, not the *safety category* of the assigned class (the
``safety_category`` field of ``NetClassRules`` in ``design_rules.py`` is
this repo's real classification SSOT). The wrong-class shape -- a
manifest-HV net assigned to an LV class, e.g. the historical
``+15V_LS -> Power`` defect or the still-open ``PWR_RTN -> GND`` case
(docs/evidence/2026-07-28-netclass-defect-reconciliation.md section 3c,
flagged for a human call) -- is deliberately NOT enforced here: enforcing
it would flag ``PWR_RTN``, whose reclassification carries an
order-of-magnitude larger blast radius and a documented placement-zone
objection (``configs/temper_production_config.yaml``). See
docs/evidence/2026-07-29-hv-netclass-coverage-gate.md's scope note and
issue temper#519 (PWR_RTN classification). The property-based tests in
test_check_hv_netclass_coverage.py pin this boundary as a metamorphic
relation: PROPERTY 1 never flags a net whose assigned class the SSOT
certifies as HV/AC, and always flags a net with no assignment.

PROPERTY 2 -- netclass rule coverage
--------------------------------------
Every class this project declares as a real, intentional netclass must
have at least one rule in ``scripts/generate_kicad_dru.py``'s GENERATED
output (not its source text -- the trace-width rules are built from an
f-string template, so a textual grep of the script would false-negative)
that POSITIVELY matches that class by name (an ``A.NetClass == 'X'`` or
``B.NetClass == 'X'`` condition). A class mentioned only negatively
(``!= 'X'``, i.e. "everything except this class"), or not mentioned at
all, enforces nothing for any net assigned to it.

"Declared as a real, intentional netclass" is the union of:
  - every key of ``TEMPER_NET_CLASSES`` (the Python placer/router's own
    net-class model), and
  - every class in ``pcb/temper.kicad_pro``'s ``net_settings.classes``
    that carries a non-empty ``description`` (this project's convention
    for a deliberately-authored safety/routing netclass, confirmed against
    every entry as of this gate's writing: ACMains, HighVoltage,
    GateDrive, HighVoltageIsolated, FinePitch and Power all carry a
    voltage/current/clearance narrative; ``Differential`` -- a
    pre-existing USB-pair length/impedance-matching class, unrelated to
    the HV/SELV safety domain this gate targets and never touched by the
    defect this gate exists to catch -- carries none),
  MINUS the two KiCad-structural classes this gate deliberately excludes
  by name (see ``STRUCTURAL_KICAD_CLASSES`` below): ``Default`` (KiCad's
  universal fallback for any net with no explicit class -- already
  covered by ``generate_kicad_dru.py``'s type-based "Default routing"
  catch-all rule, which matches ``A.Type == 'Track'``, not a netclass
  name, so it would never show up as a positive ``NetClass == 'Default'``
  match even when it is working exactly as intended) and ``Differential``
  (see above -- a real, pre-existing gap of its own, but a DIFFERENT,
  unrelated defect this task was not asked to fix; flagging it here would
  make this gate permanently red on a change nobody made).

Why ``pcb/temper.kicad_pro`` at all, and not just ``TEMPER_NET_CLASSES``:
on ``origin/main`` right now, ``HighVoltageIsolated`` is declared ONLY in
``pcb/temper.kicad_pro`` (with a real, described 6.0mm-clearance class
entry) -- it is entirely absent from ``TEMPER_NET_CLASSES``. A check
scoped to ``TEMPER_NET_CLASSES`` alone could never see it, and so could
never name it as the "declared netclass with no rules" defect it actually
is. Reading ``pcb/temper.kicad_pro`` is read-only (never written by this
gate) and is explicitly permitted; only ``pcb/temper.kicad_pcb`` (the
board file, a different file) is off-limits for WRITES -- it is read-only
input to PROPERTY 3 below, same as ``pcb/temper.kicad_pro``.

PROPERTY 3 -- kicad_pro netclass_assignments ground truth for HV nets (BLOCKING)
-----------------------------------------------------------------------------
PROPERTIES 1/2 above check the Python placer's own model
(``TEMPER_NET_ASSIGNMENTS`` / ``TEMPER_NET_CLASSES``) and, for coverage,
whether a declared class enforces anything in the generated ``.kicad_dru``.
Neither one ever reads ``pcb/temper.kicad_pro``'s
``net_settings.netclass_assignments`` -- the actual mapping ``kicad-cli``'s
DRC enforces. A net can sit in ``TEMPER_NET_ASSIGNMENTS`` (so PROPERTY 1
passes) while being completely absent from ``kicad_pro``'s real
assignments table, falling through to KiCad's ``Default`` (0.2mm) class for
every real DRC run -- invisible to both properties above. This is exactly
what happened to ``PWR_RTN`` (docs/evidence/2026-08-12-unassigned-domain-
nets.md): present in ``TEMPER_NET_ASSIGNMENTS`` (mapped to ``"GND"``, an
LV-safe class that is itself a separate, open question) but entirely absent
from ``pcb/temper.kicad_pro``'s ``netclass_assignments`` -- the file
``kicad-cli`` actually reads.

Scoped to the ``HV`` domain specifically (mirroring PROPERTIES 1/2's own
"``elec/domain_manifest.yaml`` is the SSOT for domain membership"
convention) because that is where an unassigned net silently drops HV<->LV
creepage/clearance enforcement to zero on BOTH sides of a mains crossing --
see the evidence doc Sec 6.3. Three sub-checks, all against
``elec/domain_manifest.yaml``'s ``HV`` domain list:

  3a. Every HV-domain net must exist as a real, literal net name in
      ``pcb/temper.kicad_pcb`` (structural walk, PROPERTY 3/4's shared
      ``parse_board_net_names`` -- see its docstring for why this is not a
      grep). Catches a manifest net whose spelling drifted from the board
      (the historical ``+340V_BUS`` -> ``+170V_BUS`` rename shape).
  3b. Every HV-domain net must have an entry in ``pcb/temper.kicad_pro``'s
      ``net_settings.netclass_assignments``. Catches ``PWR_RTN``.
  3c. Every HV-domain net that DOES have a ``kicad_pro`` assignment must
      resolve, via that class's ``safety_category`` in
      ``packages/temper-placer/configs/netclass_rules.yaml`` (the netclass
      parameter SSOT), to ``"HV"`` or ``"AC"`` -- never an LV-safe class.

PROPERTY 3 is evaluated (and can fail the gate) only when
``kicad_pro_path``'s JSON literally declares a
``net_settings.netclass_assignments`` mapping -- ``report.
property3_evaluated`` records whether it did. Every real KiCad project file
has this key structurally; a synthetic test fixture that omits it is
opting out of PROPERTY 3, not silently passing it (see
``TestPropertyThreeAndFour`` in the test file for the anti-vacuity check
that PROPERTY 3 really does evaluate against the live repo).

PROPERTY 4 -- the same shape for SELV, plus board-wide ghost assignments (INFORMATIONAL)
-------------------------------------------------------------------------------------
Reported, never gates the exit code. Two reasons this is informational and
PROPERTY 3 is not:

  - An SELV-domain net left unassigned still falls to ``Default`` (0.2mm),
    but KiCad DRC takes the MAX of the two nets' netclass figures for any
    pair -- so an HV<->SELV crossing stays protected as long as the HV side
    carries a real class (evidence doc Sec 6.3). The acute hazard is
    specifically an unassigned or misclassed net on the HV side; an
    unassigned SELV net is the same defect *shape* but not the same
    severity, and is reported for completeness rather than gated.
  - ``pcb/temper.kicad_pro`` carries ~37 pre-existing "ghost" assignments
    (dead net names from an earlier schematic revision, e.g. ``AC_L``/
    ``SWITCH_NODE``/``RTD_CS`` alongside the real, differently-spelled
    ``ac_l``/``SW_NODE``/``RTD_CS_N``) that
    ``scripts/sync_kicad_netclass_assignments.py``'s own docstring
    documents as deliberately, permanently kept ("It never removes an
    existing kicad_pro entry, even one that names a net no longer present
    on the board"). Gating on their presence would make this property
    permanently red for a defect nobody introduced and this task was not
    asked to clean up. Reported under ``report.ghost_kicad_pro_assignments``
    for visibility (this is the "every assignment naming a net that does
    not exist on the board" count the evidence doc's sweep reports),
    computed once across ALL of ``kicad_pro``'s assignments, not scoped to
    either domain.

Fail-closed contract (this repo's gate-family convention -- see
``check_domain_partition.py``, ``check_net_classification.py``): this
gate never exits 0 unless it positively confirms it ran a real check on
real, fresh data. It exits non-zero for every one of:
  - the domain manifest is missing, empty, malformed, or has no non-empty
    ``HV`` domain (delegates to ``check_domain_partition.load_manifest``,
    the same parser ``check_domain_partition.py`` itself trusts)
  - ``pcb/temper.kicad_pro`` is missing, not valid JSON, or has no
    non-empty ``net_settings.classes`` list
  - ``TEMPER_NET_ASSIGNMENTS`` or ``TEMPER_NET_CLASSES`` cannot be
    imported (e.g. the environment is not synced)
  - zero HV nets discovered, or zero declared netclasses discovered --
    an empty check is a broken gate, never a clean pass
  - when PROPERTY 3 is applicable (see above): ``pcb/temper.kicad_pcb``
    is missing or a structural walk finds zero top-level net
    declarations, or ``packages/temper-placer/configs/netclass_rules.yaml``
    is missing, malformed, or has no class carrying a ``safety_category``

Exit codes:
  0 - PASSED: every manifest-HV net has a netclass, every declared
      netclass has at least one positive rule in the generated DRU output,
      and (when PROPERTY 3 is applicable) every HV-domain net exists on
      the real board, has a real ``kicad_pro`` netclass assignment, and
      that assignment's safety_category is HV/AC
  3 - VIOLATION: at least one manifest-HV net has no netclass, at least
      one declared netclass has zero positive rules, or (PROPERTY 3) at
      least one HV-domain net is off-board, unassigned in
      ``kicad_pro``, or assigned an LV-safe class
  5 - GATE ERROR: the gate could not run a trustworthy check at all (see
      list above) -- never conflated with "0 violations"

Usage:
  uv run python scripts/check_hv_netclass_coverage.py
  uv run python scripts/check_hv_netclass_coverage.py --manifest PATH --kicad-pro PATH
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402
from check_domain_partition import GateError as _ManifestGateError  # noqa: E402
from check_domain_partition import load_manifest  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

REPO_ROOT = find_repo_root()
DEFAULT_MANIFEST = REPO_ROOT / "elec" / "domain_manifest.yaml"
DEFAULT_KICAD_PRO = REPO_ROOT / "pcb" / "temper.kicad_pro"
DEFAULT_KICAD_PCB = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_NETCLASS_RULES = (
    REPO_ROOT / "packages" / "temper-placer" / "configs" / "netclass_rules.yaml"
)

# KiCad-structural classes deliberately excluded from PROPERTY 2's
# "declared netclass" registry -- see the module docstring's PROPERTY 2
# section for why each one is excluded.
STRUCTURAL_KICAD_CLASSES: frozenset[str] = frozenset({"Default", "Differential"})

_NETCLASS_EQ_RE = re.compile(r"[AB]\.NetClass\s*==\s*'([^']+)'")

# PROPERTY 3/4: netclass_rules.yaml's own safety_category vocabulary is
# HV/LV/AC/iso (see GateDriveSELV's "because" comment there). 'Default' and
# 'Differential' are KiCad-structural classes with no entry in that file
# (see STRUCTURAL_KICAD_CLASSES above) -- both are LV-safe in practice
# (Default is the generic 0.2mm fallback; Differential is the USB-pair
# impedance class), so both resolve to "LV" here rather than "UNKNOWN",
# which would make an HV-domain net assigned either one report as a
# mismatch for the wrong reason (unknown category, not wrong category).
_STRUCTURAL_KICAD_SAFETY_CATEGORY: dict[str, str] = {"Default": "LV", "Differential": "LV"}

_HV_ALLOWED_SAFETY_CATEGORIES: frozenset[str] = frozenset({"HV", "AC"})
_SELV_ALLOWED_SAFETY_CATEGORIES: frozenset[str] = frozenset({"LV"})


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Property 1: HV net coverage
# ---------------------------------------------------------------------------


def load_domain_nets(manifest_path: Path, domain_name: str) -> list[str]:
    """Return the exact list of net names declared under
    ``elec/domain_manifest.yaml``'s ``domain_name`` domain, via the same
    parser ``check_domain_partition.py`` trusts (so this gate can never
    silently diverge from that gate's own idea of what a given domain
    means).

    Raises GateError (fail-closed) for every malformed-manifest case
    ``check_domain_partition.load_manifest`` itself already raises on
    (missing file, empty file, not YAML, no domains, fewer than 2
    domains, a domain with no nets, a net claimed by two domains), plus
    if there is no domain literally named ``domain_name``.
    """
    try:
        manifest = load_manifest(manifest_path)
    except _ManifestGateError as e:
        raise GateError(f"domain manifest could not be loaded: {e}") from e

    nets = manifest.domains.get(domain_name)
    if not nets:
        raise GateError(
            f"domain manifest {manifest_path} declares no non-empty "
            f"{domain_name!r} domain -- nothing to check (this gate's "
            "whole premise is that domain_manifest.yaml's domain lists "
            "are the authoritative net sets)"
        )
    return list(nets)


def load_hv_nets(manifest_path: Path) -> list[str]:
    """Return the exact list of net names declared under
    ``elec/domain_manifest.yaml``'s ``HV`` domain. See ``load_domain_nets``.
    """
    return load_domain_nets(manifest_path, "HV")


def load_selv_nets(manifest_path: Path) -> list[str]:
    """Return the exact list of net names declared under
    ``elec/domain_manifest.yaml``'s ``SELV`` domain. See
    ``load_domain_nets``. Used only by PROPERTY 4 (informational)."""
    return load_domain_nets(manifest_path, "SELV")


def check_hv_net_coverage(hv_nets: list[str], net_assignments: dict[str, Any]) -> list[str]:
    """Return the sorted list of HV-domain nets with no entry in
    ``net_assignments`` (``TEMPER_NET_ASSIGNMENTS``)."""
    return sorted(n for n in hv_nets if n not in net_assignments)


# ---------------------------------------------------------------------------
# Property 2: netclass rule coverage
# ---------------------------------------------------------------------------


def load_kicad_pro_classes(kicad_pro_path: Path) -> dict[str, str]:
    """Return {class_name: description} for every class in
    ``pcb/temper.kicad_pro``'s ``net_settings.classes``. ``description``
    is ``""`` when the field is absent or empty (both are "no real
    description" for this gate's purposes).

    Raises GateError (fail-closed) if the file is missing, not valid
    JSON, has no ``net_settings.classes`` list, that list is empty, or
    any entry has no (or an empty) ``name``.
    """
    if not kicad_pro_path.is_file():
        raise GateError(f"KiCad project file not found: {kicad_pro_path}")
    try:
        data = json.loads(kicad_pro_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GateError(f"{kicad_pro_path} is not valid JSON: {e}") from e

    classes = data.get("net_settings", {}).get("classes") if isinstance(data, dict) else None
    if not isinstance(classes, list) or not classes:
        raise GateError(
            f"{kicad_pro_path} has no non-empty 'net_settings.classes' "
            "list -- an empty or absent netclass declaration must fail "
            "the gate, not pass it vacuously"
        )

    result: dict[str, str] = {}
    for entry in classes:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise GateError(
                f"{kicad_pro_path} has a 'net_settings.classes' entry with "
                f"no 'name': {entry!r}"
            )
        result[str(entry["name"])] = str(entry.get("description") or "")
    return result


def declared_netclasses(
    net_classes: dict[str, Any], kicad_pro_classes: dict[str, str]
) -> set[str]:
    """The union of TEMPER_NET_CLASSES keys and every described,
    non-structural class declared in pcb/temper.kicad_pro -- see the
    module docstring's PROPERTY 2 section for the full justification.
    """
    declared = set(net_classes.keys())
    for name, description in kicad_pro_classes.items():
        if name in STRUCTURAL_KICAD_CLASSES:
            continue
        if description:
            declared.add(name)
    return declared


def positively_referenced_classes(dru_content: str) -> set[str]:
    """Every KiCad netclass name that appears as the right-hand side of a
    POSITIVE ``A.NetClass == 'X'`` / ``B.NetClass == 'X'`` equality test
    anywhere in the rendered ``.kicad_dru`` content. A class mentioned
    only via ``!=`` (exclusion) does not count -- see the module
    docstring for why that is not "real coverage".
    """
    return set(_NETCLASS_EQ_RE.findall(dru_content))


def check_netclass_rule_coverage(
    declared: set[str],
    kicad_class_name_fn: Callable[[str], str],
    referenced: set[str],
) -> list[str]:
    """Return the sorted list of declared (Python-key) netclass names
    whose KiCad name has zero positive rule references."""
    return sorted(
        py_key for py_key in declared if kicad_class_name_fn(py_key) not in referenced
    )


# ---------------------------------------------------------------------------
# Properties 3/4: pcb/temper.kicad_pro netclass_assignments ground truth
# ---------------------------------------------------------------------------


def _tokenize_sexpr(text: str) -> list[str]:
    """Minimal S-expression tokenizer: ``(`` / ``)`` as single-char tokens,
    double-quoted strings (surrounding quotes kept, backslash escapes
    preserved) as one token each, and any other run of non-whitespace,
    non-paren characters as a bare atom. Sufficient for a KiCad
    ``.kicad_pcb`` file's own consistent pretty-printed formatting; not a
    general Lisp reader.
    """
    tokens: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = ['"']
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append(text[j])
                    buf.append(text[j + 1])
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            buf.append('"')
            tokens.append("".join(buf))
            i = j + 1
            continue
        j = i
        while j < n and text[j] not in " \t\r\n()":
            j += 1
        tokens.append(text[i:j])
        i = j
    return tokens


def _unquote_sexpr_string(token: str) -> str:
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        return token[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return token


def parse_board_net_names(kicad_pcb_path: Path) -> set[str]:
    """Return every net name declared by a top-level ``(net N "name")``
    form -- a DIRECT child of the file's outermost ``(kicad_pcb ...)``
    form -- in *kicad_pcb_path*.

    Walked structurally by paren-depth over a real token stream, NOT by
    grepping for the literal substring ``(net``: that substring also
    matches every pad's own per-pad net reference (``(pad ... (net N
    "name"))``), nested many levels deeper. A grep or a depth-blind regex
    conflates the two and either double-counts or misattributes nets --
    the exact failure mode a prior agent's grep-based pad count hit,
    which is why this gate parses instead (see docs/evidence/
    2026-08-12-unassigned-domain-nets.md).

    Raises GateError (fail-closed) if the file is missing or the
    structural walk finds zero top-level net declarations -- an empty
    result means the parser is broken or the file is not a real
    ``.kicad_pcb``, never "the board has no nets".
    """
    if not kicad_pcb_path.is_file():
        raise GateError(f"kicad_pcb board file not found: {kicad_pcb_path}")

    tokens = _tokenize_sexpr(kicad_pcb_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    depth = 0
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        if t == "(":
            depth += 1
            # A top-level (net N "name") is a DIRECT child of the
            # outermost (kicad_pcb ...) form -- depth becomes 2 exactly
            # when we open such a child (1 for kicad_pcb itself, 2 for
            # this form). A pad's nested (net ...) reference opens at a
            # much greater depth and is deliberately not matched here.
            if depth == 2 and i + 3 < n and tokens[i + 1] == "net" and tokens[i + 3].startswith('"'):
                names.add(_unquote_sexpr_string(tokens[i + 3]))
            i += 1
            continue
        if t == ")":
            depth -= 1
            i += 1
            continue
        i += 1

    if not names:
        raise GateError(
            f"{kicad_pcb_path}: structural walk found zero top-level "
            "(net ...) declarations -- parser is broken or this is not a "
            "real .kicad_pcb file, not evidence the board has no nets"
        )
    return names


def load_kicad_pro_netclass_assignments(kicad_pro_path: Path) -> dict[str, str] | None:
    """Return ``{net: class}`` from ``pcb/temper.kicad_pro``'s
    ``net_settings.netclass_assignments`` -- the actual mapping
    ``kicad-cli``'s DRC reads.

    Returns ``None`` (not a GateError) if the key is structurally absent:
    every real KiCad project file has this key, so its absence means the
    input is a synthetic fixture opting out of PROPERTIES 3/4, not a
    malformed real file. Raises GateError if the file cannot be read, is
    not valid JSON, or the key is present but not a mapping.
    """
    if not kicad_pro_path.is_file():
        raise GateError(f"KiCad project file not found: {kicad_pro_path}")
    try:
        data = json.loads(kicad_pro_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise GateError(f"{kicad_pro_path} is not valid JSON: {e}") from e

    net_settings = data.get("net_settings", {}) if isinstance(data, dict) else {}
    raw = net_settings.get("netclass_assignments") if isinstance(net_settings, dict) else None
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise GateError(
            f"{kicad_pro_path}'s net_settings.netclass_assignments is present "
            "but not a mapping"
        )
    return {str(k): str(v) for k, v in raw.items()}


def load_netclass_safety_categories(path: Path) -> dict[str, str]:
    """Return ``{class_name: safety_category}`` from
    ``packages/temper-placer/configs/netclass_rules.yaml`` -- the netclass
    parameter SSOT (PR #1061 reconciled its VALUES against
    ``pcb/temper.kicad_pro``; this reads its ``safety_category`` field,
    a value this gate never writes) -- plus the two KiCad-structural
    classes it doesn't model (see ``_STRUCTURAL_KICAD_SAFETY_CATEGORY``).

    Raises GateError (fail-closed) if the file is missing, not valid YAML,
    has no non-empty ``classes`` mapping, or not a single declared class
    carries a ``safety_category`` field (a vacuous SSOT is a gate error,
    not "everything passes").
    """
    if not path.is_file():
        raise GateError(f"netclass rules file not found: {path}")
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise GateError(f"{path} is not valid YAML: {e}") from e

    classes = data.get("classes") if isinstance(data, dict) else None
    if not isinstance(classes, dict) or not classes:
        raise GateError(f"{path} has no non-empty 'classes' mapping")

    result = dict(_STRUCTURAL_KICAD_SAFETY_CATEGORY)
    for name, body in classes.items():
        if isinstance(body, dict) and body.get("safety_category"):
            result[str(name)] = str(body["safety_category"])

    if len(result) <= len(_STRUCTURAL_KICAD_SAFETY_CATEGORY):
        raise GateError(f"{path}: no declared class carries a 'safety_category' field")
    return result


def check_domain_nets_on_board(domain_nets: list[str], board_nets: set[str]) -> list[str]:
    """Return the sorted list of domain-declared nets absent from the
    real board's own net table -- a manifest/board spelling drift (the
    historical ``+340V_BUS`` -> ``+170V_BUS`` rename shape)."""
    return sorted(n for n in domain_nets if n not in board_nets)


def check_domain_net_kicad_pro_coverage(
    domain_nets: list[str], kicad_pro_assignments: dict[str, str]
) -> list[str]:
    """Return the sorted list of domain-declared nets with no entry in
    ``pcb/temper.kicad_pro``'s real ``netclass_assignments`` -- the
    ``PWR_RTN`` shape."""
    return sorted(n for n in domain_nets if n not in kicad_pro_assignments)


def check_domain_class_safety_mismatch(
    domain_nets: list[str],
    kicad_pro_assignments: dict[str, str],
    class_safety_category: dict[str, str],
    allowed_categories: frozenset[str],
) -> list[str]:
    """Return a sorted list of human-readable strings, one per
    domain-declared net that DOES have a ``kicad_pro`` assignment whose
    class's ``safety_category`` is not in *allowed_categories*. Nets with
    no assignment at all are skipped here -- that is
    ``check_domain_net_kicad_pro_coverage``'s violation, not this one's."""
    mismatches: list[str] = []
    for net in domain_nets:
        cls = kicad_pro_assignments.get(net)
        if cls is None:
            continue
        category = class_safety_category.get(cls, "UNKNOWN")
        if category not in allowed_categories:
            mismatches.append(f"{net!r} -> kicad_pro class {cls!r} (safety_category={category!r})")
    return sorted(mismatches)


def check_ghost_kicad_pro_assignments(
    kicad_pro_assignments: dict[str, str], board_nets: set[str]
) -> list[str]:
    """Return the sorted list of EVERY ``kicad_pro`` netclass_assignments
    key (not scoped to either domain) naming a net absent from the real
    board -- informational only, see the module docstring's PROPERTY 4
    section for why this does not gate."""
    return sorted(n for n in kicad_pro_assignments if n not in board_nets)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class Report:
    hv_nets_checked: int = 0
    unclassified_hv_nets: list[str] = field(default_factory=list)
    declared_netclasses_checked: int = 0
    classes_with_no_rules: list[str] = field(default_factory=list)
    tool_errors: list[str] = field(default_factory=list)
    # PROPERTY 3 (BLOCKING) -- HV-domain nets against pcb/temper.kicad_pro's
    # REAL netclass_assignments and the real board net table.
    property3_evaluated: bool = False
    hv_domain_nets_off_board: list[str] = field(default_factory=list)
    hv_domain_nets_unassigned_in_kicad_pro: list[str] = field(default_factory=list)
    hv_domain_class_safety_mismatches: list[str] = field(default_factory=list)
    # PROPERTY 4 (INFORMATIONAL, never gates) -- same shape for SELV, plus
    # every kicad_pro assignment (either domain) naming an off-board net.
    selv_domain_nets_off_board: list[str] = field(default_factory=list)
    selv_domain_nets_unassigned_in_kicad_pro: list[str] = field(default_factory=list)
    selv_domain_class_safety_mismatches: list[str] = field(default_factory=list)
    ghost_kicad_pro_assignments: list[str] = field(default_factory=list)
    kicad_pro_assignments_checked: int = 0


def _default_live_inputs() -> tuple[dict[str, Any], dict[str, Any], str, Callable[[str], str]]:
    """Import the real, live TEMPER_NET_CLASSES / TEMPER_NET_ASSIGNMENTS /
    generated DRU content / kicad_class_name from this repo's own
    packages. Raises GateError (fail-closed) if the environment is not
    synced (mirrors ``check_rust_drc_presence.py``'s treatment of an
    unimportable extension as a gate error, not a silent skip).
    """
    try:
        from temper_placer.core.design_rules import (  # noqa: PLC0415
            TEMPER_NET_ASSIGNMENTS,
            TEMPER_NET_CLASSES,
        )
    except ImportError as e:
        raise GateError(
            "could not import temper_placer.core.design_rules -- is the "
            f"environment synced (`uv sync`)? ({e})"
        ) from e

    try:
        from generate_kicad_dru import generate_dru, kicad_class_name  # noqa: PLC0415
    except ImportError as e:
        raise GateError(f"could not import scripts/generate_kicad_dru.py: {e}") from e

    dru_content = generate_dru()
    return dict(TEMPER_NET_CLASSES), dict(TEMPER_NET_ASSIGNMENTS), dru_content, kicad_class_name


def run(
    manifest_path: Path,
    kicad_pro_path: Path,
    net_classes: dict[str, Any] | None = None,
    net_assignments: dict[str, Any] | None = None,
    dru_content: str | None = None,
    kicad_class_name_fn: Callable[[str], str] | None = None,
    kicad_pcb_path: Path = DEFAULT_KICAD_PCB,
    netclass_rules_path: Path = DEFAULT_NETCLASS_RULES,
    board_nets: set[str] | None = None,
    class_safety_category: dict[str, str] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report), state in 'clean' | 'violation' | 'tool_error'.

    ``net_classes`` / ``net_assignments`` / ``dru_content`` /
    ``kicad_class_name_fn`` default to the real, live values imported from
    this repo's own packages -- tests override any subset of them to
    construct a mutation (an unclassified net, a class with no rules)
    without needing a second real copy of the package installed. These
    feed PROPERTIES 1/2.

    ``kicad_pcb_path`` / ``netclass_rules_path`` are real filesystem paths
    (default: this repo's own files), read live regardless of whether
    ``board_nets`` / ``class_safety_category`` are overridden --
    mirroring how ``manifest_path`` / ``kicad_pro_path`` are always read
    live for PROPERTIES 1/2. ``board_nets`` / ``class_safety_category`` let
    a test supply the parsed board net set / safety-category table
    directly instead of writing real fixture files for PROPERTIES 3/4.
    PROPERTY 3/4 activate only when ``kicad_pro_path``'s JSON declares a
    ``net_settings.netclass_assignments`` key -- see the module docstring.
    """
    report = Report()

    live_needed = (
        net_classes is None
        or net_assignments is None
        or dru_content is None
        or kicad_class_name_fn is None
    )
    if live_needed:
        try:
            (
                live_net_classes,
                live_net_assignments,
                live_dru_content,
                live_kicad_class_name,
            ) = _default_live_inputs()
        except GateError as e:
            report.tool_errors.append(str(e))
            return "tool_error", report
        net_classes = live_net_classes if net_classes is None else net_classes
        net_assignments = live_net_assignments if net_assignments is None else net_assignments
        dru_content = live_dru_content if dru_content is None else dru_content
        kicad_class_name_fn = (
            live_kicad_class_name if kicad_class_name_fn is None else kicad_class_name_fn
        )
    assert net_classes is not None
    assert net_assignments is not None
    assert dru_content is not None
    assert kicad_class_name_fn is not None

    try:
        hv_nets = load_hv_nets(manifest_path)
        kicad_pro_classes = load_kicad_pro_classes(kicad_pro_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    if not dru_content.strip():
        report.tool_errors.append(
            "scripts/generate_kicad_dru.py's generate_dru() produced empty "
            "output -- vacuous run, not a clean pass"
        )
        return "tool_error", report

    declared = declared_netclasses(net_classes, kicad_pro_classes)
    if not declared:
        report.tool_errors.append(
            "zero declared netclasses discovered across TEMPER_NET_CLASSES "
            f"and {kicad_pro_path} -- vacuous run, not a clean pass"
        )
        return "tool_error", report

    report.hv_nets_checked = len(hv_nets)
    report.declared_netclasses_checked = len(declared)

    report.unclassified_hv_nets = check_hv_net_coverage(hv_nets, net_assignments)

    referenced = positively_referenced_classes(dru_content)
    report.classes_with_no_rules = check_netclass_rule_coverage(
        declared, kicad_class_name_fn, referenced
    )

    # --- PROPERTIES 3/4: pcb/temper.kicad_pro's REAL netclass_assignments,
    # cross-referenced against the domain manifest and the real board net
    # table. See module docstring. Applicable only when kicad_pro_path's
    # JSON declares the netclass_assignments key at all.
    try:
        kicad_pro_assignments = load_kicad_pro_netclass_assignments(kicad_pro_path)
    except GateError as e:
        report.tool_errors.append(str(e))
        return "tool_error", report

    report.property3_evaluated = kicad_pro_assignments is not None
    if report.property3_evaluated:
        assert kicad_pro_assignments is not None
        report.kicad_pro_assignments_checked = len(kicad_pro_assignments)

        if board_nets is None:
            try:
                board_nets = parse_board_net_names(kicad_pcb_path)
            except GateError as e:
                report.tool_errors.append(str(e))
                return "tool_error", report

        if class_safety_category is None:
            try:
                class_safety_category = load_netclass_safety_categories(netclass_rules_path)
            except GateError as e:
                report.tool_errors.append(str(e))
                return "tool_error", report

        try:
            selv_nets = load_selv_nets(manifest_path)
        except GateError as e:
            report.tool_errors.append(str(e))
            return "tool_error", report

        # PROPERTY 3 -- HV domain, BLOCKING.
        report.hv_domain_nets_off_board = check_domain_nets_on_board(hv_nets, board_nets)
        report.hv_domain_nets_unassigned_in_kicad_pro = check_domain_net_kicad_pro_coverage(
            hv_nets, kicad_pro_assignments
        )
        report.hv_domain_class_safety_mismatches = check_domain_class_safety_mismatch(
            hv_nets, kicad_pro_assignments, class_safety_category, _HV_ALLOWED_SAFETY_CATEGORIES
        )

        # PROPERTY 4 -- SELV domain + board-wide ghosts, INFORMATIONAL.
        report.selv_domain_nets_off_board = check_domain_nets_on_board(selv_nets, board_nets)
        report.selv_domain_nets_unassigned_in_kicad_pro = check_domain_net_kicad_pro_coverage(
            selv_nets, kicad_pro_assignments
        )
        report.selv_domain_class_safety_mismatches = check_domain_class_safety_mismatch(
            selv_nets,
            kicad_pro_assignments,
            class_safety_category,
            _SELV_ALLOWED_SAFETY_CATEGORIES,
        )
        report.ghost_kicad_pro_assignments = check_ghost_kicad_pro_assignments(
            kicad_pro_assignments, board_nets
        )

    if (
        report.unclassified_hv_nets
        or report.classes_with_no_rules
        or report.hv_domain_nets_off_board
        or report.hv_domain_nets_unassigned_in_kicad_pro
        or report.hv_domain_class_safety_mismatches
    ):
        return "violation", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        "HV netclass coverage gate -- "
        f"{report.hv_nets_checked} HV-domain net(s) checked against "
        "TEMPER_NET_ASSIGNMENTS, "
        f"{report.declared_netclasses_checked} declared netclass(es) "
        "checked against scripts/generate_kicad_dru.py's generated rules"
    )

    if report.tool_errors:
        print(f"\n{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e}")

    print(
        f"\n=== PROPERTY 1: UNCLASSIFIED HV NETS: {len(report.unclassified_hv_nets)} ==="
    )
    for net in report.unclassified_hv_nets:
        print(
            f"  VIOLATION net {net!r} is declared under elec/domain_manifest.yaml's "
            "HV domain but has NO entry in TEMPER_NET_ASSIGNMENTS -- it silently "
            "falls through to DesignRules' LV default clearance/creepage"
        )

    print(
        f"\n=== PROPERTY 2: NETCLASSES WITH NO RULES: {len(report.classes_with_no_rules)} ==="
    )
    for cls in report.classes_with_no_rules:
        print(
            f"  VIOLATION netclass {cls!r} is a declared netclass (TEMPER_NET_CLASSES "
            "and/or pcb/temper.kicad_pro) but scripts/generate_kicad_dru.py's "
            "generated output contains zero rules positively matching "
            f"NetClass == {cls!r} -- this class enforces nothing for any net "
            "assigned to it"
        )

    if not report.property3_evaluated:
        print(
            "\n=== PROPERTIES 3/4: NOT EVALUATED (kicad_pro has no "
            "net_settings.netclass_assignments key) ==="
        )
    else:
        print(
            f"\n=== PROPERTY 3 (BLOCKING): HV-domain nets vs pcb/temper.kicad_pro's "
            f"REAL netclass_assignments ({report.kicad_pro_assignments_checked} "
            "assignment(s) on file) ==="
        )
        print(f"  off-board HV-domain nets: {len(report.hv_domain_nets_off_board)}")
        for net in report.hv_domain_nets_off_board:
            print(
                f"    VIOLATION net {net!r} is declared under elec/domain_manifest.yaml's "
                "HV domain but is NOT a real net on pcb/temper.kicad_pcb"
            )
        print(
            f"  unassigned in kicad_pro: {len(report.hv_domain_nets_unassigned_in_kicad_pro)}"
        )
        for net in report.hv_domain_nets_unassigned_in_kicad_pro:
            print(
                f"    VIOLATION net {net!r} is declared under elec/domain_manifest.yaml's "
                "HV domain but has NO entry in pcb/temper.kicad_pro's "
                "net_settings.netclass_assignments -- falls to Default (0.2mm), "
                "invisible to every HV<->SELV clearance/creepage rule"
            )
        print(f"  wrong-safety-category assignments: {len(report.hv_domain_class_safety_mismatches)}")
        for msg in report.hv_domain_class_safety_mismatches:
            print(f"    VIOLATION {msg}")

        print(
            "\n=== PROPERTY 4 (INFORMATIONAL, non-blocking): SELV-domain sweep + "
            "board-wide ghost assignments ==="
        )
        print(f"  off-board SELV-domain nets: {len(report.selv_domain_nets_off_board)}")
        for net in report.selv_domain_nets_off_board:
            print(f"    INFO net {net!r} (SELV domain) is not a real net on pcb/temper.kicad_pcb")
        print(
            f"  SELV-domain nets unassigned in kicad_pro: "
            f"{len(report.selv_domain_nets_unassigned_in_kicad_pro)}"
        )
        for net in report.selv_domain_nets_unassigned_in_kicad_pro:
            print(f"    INFO net {net!r} (SELV domain) has no kicad_pro netclass assignment")
        print(f"  SELV wrong-safety-category assignments: {len(report.selv_domain_class_safety_mismatches)}")
        for msg in report.selv_domain_class_safety_mismatches:
            print(f"    INFO {msg}")
        print(f"  ghost kicad_pro assignments (either domain): {len(report.ghost_kicad_pro_assignments)}")
        for net in report.ghost_kicad_pro_assignments[:10]:
            print(f"    INFO {net!r} has a kicad_pro netclass assignment but no real board net")
        if len(report.ghost_kicad_pro_assignments) > 10:
            print(f"    ... and {len(report.ghost_kicad_pro_assignments) - 10} more")

    if state == "clean":
        print("\nHV netclass coverage gate passed")
    elif state == "violation":
        print(
            f"\nFAILED -- {len(report.unclassified_hv_nets)} unclassified HV net(s) "
            "(PROPERTY 1), "
            f"{len(report.classes_with_no_rules)} netclass(es) with no rules "
            "(PROPERTY 2), "
            f"{len(report.hv_domain_nets_off_board)} off-board HV-domain net(s), "
            f"{len(report.hv_domain_nets_unassigned_in_kicad_pro)} HV-domain net(s) "
            "unassigned in kicad_pro, "
            f"{len(report.hv_domain_class_safety_mismatches)} HV-domain class "
            "safety-category mismatch(es) (PROPERTY 3)"
        )
    else:
        print(
            "\nGATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--kicad-pro", type=Path, default=DEFAULT_KICAD_PRO)
    args = parser.parse_args()

    state, report = run(args.manifest, args.kicad_pro)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### HV Netclass Coverage Gate: {state}\n")
            f.write(
                f"- HV-domain nets checked: {report.hv_nets_checked}\n"
                f"- Unclassified HV nets: {len(report.unclassified_hv_nets)}\n"
                f"- Declared netclasses checked: {report.declared_netclasses_checked}\n"
                f"- Netclasses with no rules: {len(report.classes_with_no_rules)}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
            )
            if report.unclassified_hv_nets:
                f.write("\nUnclassified HV nets:\n")
                for net in report.unclassified_hv_nets:
                    f.write(f"- `{net}`\n")
            if report.classes_with_no_rules:
                f.write("\nNetclasses with no rules:\n")
                for cls in report.classes_with_no_rules:
                    f.write(f"- `{cls}`\n")
            f.write(
                f"\n- PROPERTY 3/4 evaluated: {report.property3_evaluated}\n"
                f"- HV-domain nets off-board: {len(report.hv_domain_nets_off_board)}\n"
                f"- HV-domain nets unassigned in kicad_pro: "
                f"{len(report.hv_domain_nets_unassigned_in_kicad_pro)}\n"
                f"- HV-domain class safety-category mismatches: "
                f"{len(report.hv_domain_class_safety_mismatches)}\n"
                f"- (informational) SELV-domain nets unassigned in kicad_pro: "
                f"{len(report.selv_domain_nets_unassigned_in_kicad_pro)}\n"
                f"- (informational) ghost kicad_pro assignments: "
                f"{len(report.ghost_kicad_pro_assignments)}\n"
            )
            if report.hv_domain_nets_unassigned_in_kicad_pro:
                f.write("\nHV-domain nets unassigned in kicad_pro:\n")
                for net in report.hv_domain_nets_unassigned_in_kicad_pro:
                    f.write(f"- `{net}`\n")

    if state == "tool_error":
        sys.exit(EXIT_GATE_ERROR)
    if state == "violation":
        sys.exit(EXIT_VIOLATION)
    sys.exit(EXIT_OK)


if __name__ == "__main__":
    main()
