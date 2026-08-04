"""Load netclass_rules.yaml into a DesignRules instance.

Delegation shim (Wave 4 Phase 3): the YAML parse and field mapping live in
Rust (`temper_design_bundle_python.load_netclass_rules`, see
packages/temper-design-bundle/src/netclass_loader.rs). This module keeps the
`NetClassRulesDict` dataclass wrapper (KTD7) and the file reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from temper_design_bundle_python import load_netclass_rules as _load_netclass_rules

from temper_placer.core.design_rules import DesignRules


@dataclass
class NetClassRulesDict:
    """Convenience wrapper returned by load_netclass_rules()."""

    design_rules: DesignRules
    class_pairs: dict[tuple[str, str], dict] = field(
        default_factory=dict
    )  # (A,B) sorted -> {clearance, because}


def load_netclass_rules(path: Path) -> NetClassRulesDict:
    """Load netclass_rules.yaml and populate a DesignRules instance.

    Returns NetClassRulesDict with:
    - design_rules: DesignRules with net_classes populated from YAML classes
    - class_pairs: dict of (class_a, class_b) sorted -> {clearance, because}
    """
    design_rules, class_pairs = _load_netclass_rules(path.read_text())
    return NetClassRulesDict(design_rules=design_rules, class_pairs=class_pairs)
