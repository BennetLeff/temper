from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
import re

@dataclass
class DRCViolation:
    """Raw DRC violation data from KiCad."""
    type: str
    items: List[str] = field(default_factory=list)
    severity: str = "error"
    description: str = ""
    pos: Optional[Tuple[float, float]] = None
    required: Optional[float] = None
    actual: Optional[float] = None

@dataclass
class MappedViolation:
    """DRC violation mapped to PCB components and zones."""
    type: str
    components: List[str]
    position: Optional[Tuple[float, float]] = None
    zone: Optional[str] = None
    required_clearance: Optional[float] = None
    actual_clearance: Optional[float] = None
    involves_via: bool = False
    involves_pth: bool = False
    description: str = ""

class ViolationComponentMapper:
    """Analyzes DRC violations to identify responsible components and zones."""
    
    def __init__(self, netlist, zone_config: Optional[Dict[str, Any]] = None):
        """
        Initialize mapper.
        
        Args:
            netlist: Netlist object containing components.
            zone_config: Dictionary mapping zone names to their bounds.
        """
        self.netlist = netlist
        self.zone_config = zone_config or {}
        self.component_refs = {c.ref for c in netlist.components}
        
    def map_violation(self, violation: DRCViolation) -> MappedViolation:
        """
        Map a raw violation to components and zones.
        
        Args:
            violation: Raw DRCViolation object.
            
        Returns:
            MappedViolation object.
        """
        components = set()
        involves_via = False
        involves_pth = False
        
        # 1. Parse component references from items
        for item in violation.items:
            # Look for "of <REF>" (KiCad standard)
            match = re.search(r'of ([A-Za-z0-9_]+)', item, re.IGNORECASE)
            if match:
                ref = match.group(1)
                if ref in self.component_refs:
                    components.add(ref)
            
            # Look for "Pad <REF>-<PIN>" (Some formats)
            match = re.search(r'pad ([A-Za-z0-9_]+)-', item, re.IGNORECASE)
            if match:
                ref = match.group(1)
                if ref in self.component_refs:
                    components.add(ref)
            
            # Look for "Pad <REF>." (Some formats)
            match = re.search(r'pad ([A-Za-z0-9_]+)\.', item, re.IGNORECASE)
            if match:
                ref = match.group(1)
                if ref in self.component_refs:
                    components.add(ref)

            if "Via" in item or "via" in item.lower():
                involves_via = True
            if "PTH" in item or "pth" in item.lower():
                involves_pth = True

        # 2. Extract position from violation if not explicitly set
        pos = violation.pos
        
        # 3. Determine zone from position
        zone = None
        if pos and self.zone_config:
            for zone_name, config in self.zone_config.items():
                bounds = config.get('bounds')
                if bounds:
                    # TDD expects bounds to be a list of two points [(x1, y1), (x2, y2)]
                    if len(bounds) == 2:
                        (x1, y1), (x2, y2) = bounds
                        # Support both (min, max) and (p1, p2) orders
                        min_x, max_x = min(x1, x2), max(x1, x2)
                        min_y, max_y = min(y1, y2), max(y1, y2)
                        
                        if min_x <= pos[0] <= max_x and min_y <= pos[1] <= max_y:
                            zone = zone_name
                            break
        
        # 4. Extract clearance info from description if not already set
        required = violation.required
        actual = violation.actual
        
        if (required is None or actual is None) and violation.description:
            # Common clearance description: "Clearance violation (0.15mm < 0.20mm required)"
            match = re.search(r'([\d\.]+)mm < ([\d\.]+)mm required', violation.description)
            if match:
                actual = float(match.group(1))
                required = float(match.group(2))
            else:
                # KiCad JSON style: "clearance 0.2000 mm; actual 0.1958 mm"
                match = re.search(r'clearance ([\d\.]+) mm; actual ([\d\.]+) mm', violation.description)
                if match:
                    required = float(match.group(1))
                    actual = float(match.group(2))
        
        return MappedViolation(
            type=violation.type,
            components=sorted(list(components)),
            position=pos,
            zone=zone,
            required_clearance=required,
            actual_clearance=actual,
            involves_via=involves_via,
            involves_pth=involves_pth,
            description=violation.description
        )
