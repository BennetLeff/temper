"""Per-net-PAIR CREEPAGE for the A* obstacle map, in the routing DECISION.

Reads ``configs/pair_creepage.generated.yaml`` -- emitted by
``scripts/generate_kicad_dru.py`` by evaluating the creepage rules it just
wrote into ``pcb/temper.kicad_dru`` under KiCad's own
last-matching-rule-wins precedence (the same derivation route the zone-pour
creepage table ``zone_pour_creepage.generated.yaml`` already proved) -- so
the router's obstacle halos are decided against the same figures kicad-cli's
DRC engine grades by.

WHY THE A* NEEDS A CREEPAGE PAIR TABLE (2026-08-16):

The N-layer A* built its occupancy grids with a CLEARANCE halo around every
obstacle (0.2mm -- the RULE 10 track-involving floor) and stamped routed
copper at the pair members' clearances. The DRC grades HV<->LV pairs at
**12.6mm** creepage (PD3 reinforced -- the as-built bar,
``docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md``), so an HV
track could thread 0.2mm from an LV pad and pass every router check while
failing the board's own DRC: measured as ~300 pad<->track / track<->track
creepage violations on the 6-layer routed board (see
``docs/evidence/2026-08-16-creepage-aware-cspace.md``). The pair-clearance
table (``pair_clearance.py``) only knows CLEARANCE -- resolving HV<->LV to
2.0mm -- so the obstacle map could not express the 12.6mm creepage bar.

A pair no creepage rule matches resolves to **0.0** in this table: KiCad's
DRC applies no creepage check to such a pair, so the obstacle map must not
charge a creepage halo that does not exist; the clearance floor still
protects that pair at its clearance number (the caller takes
``max(clearance, creepage)``).

The table is type-independent: every creepage rule's condition references
only NetClass (never Type/Reference), so the Track<->Track world the
generator resolves the matrix in grades a Pad<->Track or Track<->Via pair
of the same two classes identically -- verified in the generator's own
comment block on PAIR_CREEPAGE_MATRIX_PATH.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from temper_placer.router_v6.pair_clearance import (
    UNASSIGNED_NETCLASS,
    kicad_class_name,
)

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "pair_creepage.generated.yaml"
)


@dataclass(frozen=True)
class PairCreepageTable:
    """``{(class_a, class_b): required_mm}``, symmetric.

    ``required`` never raises: an unknown class resolves to
    :data:`UNASSIGNED_NETCLASS` (the same treatment KiCad gives a net with
    no net-class assignment), and a pair with no entry at all resolves to
    ``0.0`` -- the DRU declares no creepage requirement for it (the caller
    combines with the clearance figure via ``max``).
    """

    pairs: dict[tuple[str, str], float]
    classes: tuple[str, ...]

    def _key_class(self, class_name: str | None) -> str:
        key = kicad_class_name(class_name or UNASSIGNED_NETCLASS)
        return key if key in self.classes else UNASSIGNED_NETCLASS

    def required(self, class_a: str | None, class_b: str | None) -> float:
        """Required edge-to-edge CREEPAGE in mm between two net classes.

        ``0.0`` means the DRU declares no creepage requirement for this
        pair -- the caller must not charge a creepage halo for it.
        """
        key_a = self._key_class(class_a)
        key_b = self._key_class(class_b)
        value = self.pairs.get((key_a, key_b))
        if value is None:
            value = self.pairs.get((key_b, key_a))
        return value if value is not None else 0.0

    def self_creepage(self, class_name: str | None) -> float:
        """Creepage between two different nets of the same class."""
        return self.required(class_name, class_name)


def load_pair_creepage_table(path: Path | str | None = None) -> PairCreepageTable:
    """Load :data:`_DEFAULT_CONFIG_PATH` (or *path*) into a table."""
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    classes = tuple(raw["classes"])
    pairs: dict[tuple[str, str], float] = {}
    for key, value in raw["pairs"].items():
        class_a, _, class_b = key.partition("|")
        pairs[(class_a, class_b)] = float(value)
        pairs[(class_b, class_a)] = float(value)
    return PairCreepageTable(pairs=pairs, classes=classes)


@lru_cache(maxsize=4)
def _cached_table(path: str | None) -> PairCreepageTable:
    return load_pair_creepage_table(path)


def default_creepage_table() -> PairCreepageTable:
    """The generated table, parsed once per process."""
    return _cached_table(None)


def net_class_of(net_name: str | None, design_rules) -> str:
    """The router-side net-class name a net resolves to.

    ``design_rules`` is any duck-compatible rules object with a
    ``net_class_assignments`` mapping (the stage0 dataclass or the core
    pyo3 pyclass); an unassigned net resolves to :data:`UNASSIGNED_NETCLASS`
    -- the same fallback ``get_rules_for_net`` uses and the class KiCad's
    DRC reports for it.
    """
    if not net_name:
        return UNASSIGNED_NETCLASS
    assignments = getattr(design_rules, "net_class_assignments", None) or {}
    return assignments.get(net_name) or UNASSIGNED_NETCLASS
