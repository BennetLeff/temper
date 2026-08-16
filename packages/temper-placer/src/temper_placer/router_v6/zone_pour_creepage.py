"""Per-net-PAIR CREEPAGE for ZONE POURS, in the emitted geometry.

Twin of :mod:`zone_pour_clearance` for the CREEPAGE constraint.  Both
read ``configs/zone_pour_creepage.generated.yaml`` /
``configs/zone_pour_clearance.generated.yaml`` -- emitted by
``scripts/generate_kicad_dru.py`` by evaluating the rules it just wrote
into ``pcb/temper.kicad_dru`` under KiCad's last-matching-rule-wins
precedence, so a pour built against these tables is decided against the
same figures kicad-cli's DRC engine and zone filler will judge it by.

WHY CREEPAGE NEEDS ITS OWN TABLE (and why the carve is max(clearance,
creepage), not either alone):

* The DRU *clearance* table resolves HV-vs-LV to **2.0 mm**.  The DRC
  judges HV-vs-LV **creepage** at **12.6 mm** (PD3 reinforced -- the
  as-built bar, ``docs/evidence/2026-08-15-pd2-pd3-data-driven-
  decision.md``).  A pour carved at 2.0 mm from a +3V3 pad fills copper
  2.0 mm from it and violates the 12.6 mm creepage rule -- exactly the
  measured "+170V_BUS pour 2.0 mm from +3V3 pad of U16" family the
  2026-08-15 DRC classification recorded (docs/evidence/2026-08-15-rust-
  zone-pour-design.md, section 4).
* Measured against this board: the same gnd pour carved at 2.0 mm has
  min gap **2.00 mm** to HV pads (a violation); carved at 12.6 mm it has
  min gap **12.58 mm** (passes).  The outline must subtract *pair
  creepage* halos wherever creepage exceeds clearance -- which for every
  HV-involving pair it does.
* A pair no creepage rule matches resolves to **0.0** in this table:
  KiCad's DRC applies no creepage check to such a pair, so the pour must
  not be carved back for a creepage figure that does not exist; the
  clearance twin still protects that pair at its clearance number.

The zone's own ``(clearance ...)`` scalar carries the *minimum* pair
requirement (unchanged, from ``zone_pour_clearance.min_required``) --
KiCad only consults it where no custom rule matches.  The per-pair
figure lives in the carved outline, where a single scalar cannot erase
it; ``_emit_zone_pours`` passes each obstacle ``max(clearance, creepage)``
to ``temper_geometry.pour_outline_py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from temper_placer.router_v6.zone_pour_clearance import (
    OTHER_TYPES,
    UNASSIGNED_NETCLASS,
    kicad_class_name,
)

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "zone_pour_creepage.generated.yaml"
)


@dataclass(frozen=True)
class ZonePourCreepageTable:
    """``{(zone_class, other_class, other_type): required_mm}``.

    ``required`` never raises.  An unknown class resolves to
    :data:`UNASSIGNED_NETCLASS` (the same treatment KiCad gives a net
    with no net-class assignment) and an unknown item type resolves to
    the strictest figure the pair carries across the types the table
    does name -- the same convention as
    :class:`zone_pour_clearance.ZonePourClearanceTable`.  A pair no
    creepage rule matches resolves to ``0.0`` (no creepage requirement);
    the caller combines with the clearance table via ``max``.
    """

    values: dict[tuple[str, str, str], float]
    classes: tuple[str, ...]

    def _key_class(self, name: str | None) -> str:
        key = kicad_class_name(name or UNASSIGNED_NETCLASS)
        return key if key in self.classes else UNASSIGNED_NETCLASS

    def required(
        self,
        zone_class: str | None,
        other_class: str | None,
        other_type: str = "Track",
    ) -> float:
        """Required edge-to-edge CREEPAGE in mm between a pour and an item.

        ``0.0`` means the DRU declares no creepage requirement for this
        pair -- the carve must fall back to the clearance table.
        """
        key_a = self._key_class(zone_class)
        key_b = self._key_class(other_class)
        value = self.values.get((key_a, key_b, other_type))
        if value is not None:
            return value
        across = [
            self.values[(key_a, key_b, t)] for t in OTHER_TYPES if (key_a, key_b, t) in self.values
        ]
        return max(across) if across else 0.0


def load_zone_pour_creepage_table(
    path: Path | str | None = None,
) -> ZonePourCreepageTable:
    """Load :data:`_DEFAULT_CONFIG_PATH` (or *path*) into a table."""
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    classes = tuple(raw["classes"])
    values: dict[tuple[str, str, str], float] = {}
    for key, per_type in raw["pairs"].items():
        zone_class, _, other_class = key.partition("|")
        for item_type, value in per_type.items():
            values[(zone_class, other_class, item_type)] = float(value)
    return ZonePourCreepageTable(values=values, classes=classes)


@lru_cache(maxsize=4)
def _cached_table(path: str | None) -> ZonePourCreepageTable:
    return load_zone_pour_creepage_table(path)


def default_creepage_table() -> ZonePourCreepageTable:
    """The generated table, parsed once per process."""
    return _cached_table(None)
