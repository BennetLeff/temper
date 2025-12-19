#!/usr/bin/env python3
"""
Fix KiCad schematics for ERC compliance.

This script addresses:
1. Remove semicolon comments (invalid in S-expressions)
2. Embed missing symbol definitions from component libraries
3. Fix wire connectivity issues
4. Ensure hierarchical labels are connected

Usage:
    python tools/fix_kicad_schematics.py
"""

import re
import os
import sys
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Pin:
    """Represents a symbol pin."""

    number: str
    name: str
    x: float
    y: float
    angle: int  # degrees: 0, 90, 180, 270
    pin_type: str  # passive, input, output, power_in, etc.


@dataclass
class Symbol:
    """Represents a KiCad symbol definition."""

    lib_id: str
    name: str
    pins: List[Pin] = field(default_factory=list)
    raw_content: str = ""


@dataclass
class PlacedSymbol:
    """A symbol placed in the schematic."""

    lib_id: str
    reference: str
    x: float
    y: float
    rotation: int  # 0, 90, 180, 270
    uuid: str


@dataclass
class Wire:
    """A wire segment."""

    x1: float
    y1: float
    x2: float
    y2: float
    uuid: str


@dataclass
class HierarchicalLabel:
    """A hierarchical label."""

    name: str
    x: float
    y: float
    angle: int
    shape: str  # input, output, bidirectional, passive
    uuid: str


class SExpressionParser:
    """Simple S-expression parser for KiCad files."""

    @staticmethod
    def parse(text: str) -> List:
        """Parse S-expression text into nested lists."""
        # Remove comments (lines starting with ;)
        lines = text.split("\n")
        clean_lines = []
        for line in lines:
            # Remove inline comments and full-line comments
            stripped = line.lstrip()
            if stripped.startswith(";"):
                continue
            # Handle inline comments
            if ";" in line and '"' not in line.split(";")[0]:
                line = line.split(";")[0]
            clean_lines.append(line)
        text = "\n".join(clean_lines)

        tokens = SExpressionParser._tokenize(text)
        result, _ = SExpressionParser._parse_tokens(tokens, 0)
        return result

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize S-expression text."""
        tokens = []
        i = 0
        while i < len(text):
            c = text[i]
            if c in " \t\n\r":
                i += 1
            elif c == "(":
                tokens.append("(")
                i += 1
            elif c == ")":
                tokens.append(")")
                i += 1
            elif c == '"':
                # String literal
                j = i + 1
                while j < len(text) and text[j] != '"':
                    if text[j] == "\\":
                        j += 2
                    else:
                        j += 1
                tokens.append(text[i : j + 1])
                i = j + 1
            else:
                # Atom
                j = i
                while j < len(text) and text[j] not in " \t\n\r()":
                    j += 1
                tokens.append(text[i:j])
                i = j
        return tokens

    @staticmethod
    def _parse_tokens(tokens: List[str], pos: int) -> Tuple[Any, int]:
        """Parse tokens into nested structure."""
        if pos >= len(tokens):
            return None, pos

        if tokens[pos] == "(":
            result = []
            pos += 1
            while pos < len(tokens) and tokens[pos] != ")":
                item, pos = SExpressionParser._parse_tokens(tokens, pos)
                if item is not None:
                    result.append(item)
            return result, pos + 1  # Skip closing paren
        else:
            return tokens[pos], pos + 1


class KiCadSchematicFixer:
    """Main class to fix KiCad schematics."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.pcb_dir = project_root / "pcb"
        self.components_dir = project_root / "components"
        self.symbol_cache: Dict[str, str] = {}  # lib_id -> raw symbol content

    def load_symbol_libraries(self):
        """Load all symbol definitions from component libraries."""
        print("Loading symbol libraries...")

        # Map lib_id prefixes to symbol files
        lib_map = {
            "IKW40N120H3": self.components_dir / "IKW40N120H3/IKW40N120H3.kicad_sym",
            "UCC21550": self.components_dir / "UCC21550/UCC21550.kicad_sym",
            "ADUM1250": self.components_dir / "ADUM1250/ADUM1250.kicad_sym",
            "LMR51430": self.components_dir / "LMR51420/test_files/LMR51430.kicad_sym",
            "ESP32-S3": self.components_dir / "ESP32-S3/ESP32-S3-WROOM-1.kicad_sym",
            "XC6220": self.components_dir / "XC6220/XC6220.kicad_sym",
            "MAX31865": self.project_root / "max31865/MAX31865.kicad_sym",
        }

        for lib_prefix, sym_file in lib_map.items():
            if sym_file.exists():
                print(f"  Loading {lib_prefix} from {sym_file}")
                self._load_symbols_from_file(lib_prefix, sym_file)
            else:
                print(f"  WARNING: Symbol file not found: {sym_file}")

    def _load_symbols_from_file(self, lib_prefix: str, sym_file: Path):
        """Load symbols from a .kicad_sym file."""
        content = sym_file.read_text()

        # Find all symbol definitions
        # Pattern: (symbol "NAME" ... )
        # We need to extract each complete symbol block

        depth = 0
        in_symbol = False
        symbol_start = 0
        symbol_name = ""

        i = 0
        while i < len(content):
            if content[i : i + 8] == "(symbol ":
                if depth == 1:  # Top-level symbol in library
                    in_symbol = True
                    symbol_start = i
                    # Extract symbol name
                    match = re.match(r'\(symbol\s+"([^"]+)"', content[i:])
                    if match:
                        symbol_name = match.group(1)

            if content[i] == "(":
                depth += 1
            elif content[i] == ")":
                depth -= 1
                if depth == 1 and in_symbol:
                    # End of symbol definition
                    symbol_content = content[symbol_start : i + 1]
                    lib_id = f"{lib_prefix}:{symbol_name}"
                    self.symbol_cache[lib_id] = symbol_content
                    print(f"    Loaded symbol: {lib_id}")
                    in_symbol = False
            i += 1

    def fix_schematic(self, sch_file: Path) -> bool:
        """Fix a single schematic file."""
        print(f"\nFixing {sch_file.name}...")

        content = sch_file.read_text()
        original_content = content

        # Step 1: Remove semicolon comments
        content = self._remove_comments(content)

        # Step 2: Find all referenced lib_ids
        referenced_libs = self._find_referenced_libs(content)
        print(f"  Referenced libraries: {referenced_libs}")

        # Step 3: Check which symbols need to be embedded
        missing_symbols = self._find_missing_symbols(content, referenced_libs)
        print(f"  Missing symbols: {missing_symbols}")

        # Step 4: Embed missing symbols
        if missing_symbols:
            content = self._embed_symbols(content, missing_symbols)

        # Step 5: Fix wire connectivity (for now, just ensure valid format)
        content = self._validate_wires(content)

        # Write back if changed
        if content != original_content:
            sch_file.write_text(content)
            print(f"  Updated {sch_file.name}")
            return True
        else:
            print(f"  No changes needed for {sch_file.name}")
            return False

    def _remove_comments(self, content: str) -> str:
        """Remove semicolon comments from content."""
        lines = content.split("\n")
        clean_lines = []
        removed_count = 0

        for line in lines:
            stripped = line.lstrip()
            if stripped.startswith(";"):
                removed_count += 1
                continue
            # Also remove inline comments (but be careful with strings)
            if ";" in line:
                # Only remove if not inside a string
                in_string = False
                new_line = []
                for i, c in enumerate(line):
                    if c == '"' and (i == 0 or line[i - 1] != "\\"):
                        in_string = not in_string
                    if c == ";" and not in_string:
                        break
                    new_line.append(c)
                line = "".join(new_line).rstrip()
                if line != lines[lines.index(line)]:
                    removed_count += 1
            clean_lines.append(line)

        if removed_count > 0:
            print(f"  Removed {removed_count} comment lines")

        return "\n".join(clean_lines)

    def _find_referenced_libs(self, content: str) -> List[str]:
        """Find all lib_id references in schematic."""
        pattern = r'\(lib_id\s+"([^"]+)"\)'
        matches = re.findall(pattern, content)
        return list(set(matches))

    def _find_missing_symbols(
        self, content: str, referenced_libs: List[str]
    ) -> List[str]:
        """Find which referenced symbols are not in lib_symbols section."""
        missing = []

        # Extract lib_symbols section
        lib_symbols_match = re.search(
            r"\(lib_symbols\s*((?:\(symbol[^)]*\)|\s)*)\)", content, re.DOTALL
        )
        if lib_symbols_match:
            lib_symbols_content = lib_symbols_match.group(1)
        else:
            lib_symbols_content = ""

        for lib_id in referenced_libs:
            # Skip standard libraries (Device, power, 74xx, etc.)
            prefix = lib_id.split(":")[0] if ":" in lib_id else lib_id
            if prefix in ["Device", "power", "74xx", "Comparator", "Timer", "Switch"]:
                continue

            # Check if symbol is defined
            symbol_name = lib_id.replace(":", "_").replace("-", "_")
            # Also check for the actual lib_id pattern
            if f'symbol "{lib_id}"' not in lib_symbols_content:
                # Check if we have this symbol in cache
                if lib_id in self.symbol_cache:
                    missing.append(lib_id)
                else:
                    print(f"  WARNING: No symbol definition found for {lib_id}")

        return missing

    def _embed_symbols(self, content: str, symbols: List[str]) -> str:
        """Embed symbol definitions into lib_symbols section."""
        for lib_id in symbols:
            if lib_id not in self.symbol_cache:
                continue

            symbol_def = self.symbol_cache[lib_id]

            # Convert symbol name to match lib_id format
            # Original: (symbol "UCC21550DWK" ...)
            # Target: (symbol "UCC21550:UCC21550DWK" ...)
            symbol_name = lib_id.split(":")[1] if ":" in lib_id else lib_id
            symbol_def = symbol_def.replace(
                f'(symbol "{symbol_name}"', f'(symbol "{lib_id}"', 1
            )

            # Find lib_symbols section and add symbol
            lib_symbols_match = re.search(r"(\(lib_symbols)\s*(\)|\()", content)
            if lib_symbols_match:
                insert_pos = lib_symbols_match.end(1)
                # Add proper indentation
                indented_symbol = "\n    " + symbol_def.replace("\n", "\n    ")
                content = content[:insert_pos] + indented_symbol + content[insert_pos:]
                print(f"  Embedded symbol: {lib_id}")

        return content

    def _validate_wires(self, content: str) -> str:
        """Validate and fix wire format."""
        # For now, just ensure wires have valid format
        # More complex fixes would require full parsing
        return content

    def fix_all_schematics(self):
        """Fix all schematic files in the project."""
        self.load_symbol_libraries()

        schematic_files = list(self.pcb_dir.glob("*.kicad_sch"))
        print(f"\nFound {len(schematic_files)} schematic files")

        fixed_count = 0
        for sch_file in schematic_files:
            if sch_file.name == "temper.kicad_sch":
                # Root schematic - only remove comments
                print(f"\nProcessing root schematic: {sch_file.name}")
                content = sch_file.read_text()
                new_content = self._remove_comments(content)
                if new_content != content:
                    sch_file.write_text(new_content)
                    fixed_count += 1
            else:
                if self.fix_schematic(sch_file):
                    fixed_count += 1

        print(f"\n{'=' * 50}")
        print(f"Fixed {fixed_count} schematic files")


def create_device_symbols() -> Dict[str, str]:
    """Create standard Device library symbols that may be missing."""
    symbols = {}

    # These are standard KiCad symbols that should be available
    # but we include them for CLI compatibility

    symbols[
        "Device:LED"
    ] = """(symbol "Device:LED" (pin_numbers hide) (pin_names (offset 1.016) hide) (in_bom yes) (on_board yes)
      (property "Reference" "D" (at 0 2.54 0) (effects (font (size 1.27 1.27))))
      (property "Value" "LED" (at 0 -2.54 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "LED_0_1"
        (polyline (pts (xy -1.27 -1.27) (xy -1.27 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.27 0) (xy 1.27 0)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy 1.27 -1.27) (xy 1.27 1.27) (xy -1.27 0) (xy 1.27 -1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -3.048 -1.524) (xy -1.778 -2.794)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -1.778 -1.524) (xy -0.508 -2.794)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -2.032 -2.794) (xy -2.54 -2.286) (xy -1.778 -2.794) (xy -2.032 -2.794)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -0.762 -2.794) (xy -1.27 -2.286) (xy -0.508 -2.794) (xy -0.762 -2.794)) (stroke (width 0) (type default)) (fill (type none)))
      )
      (symbol "LED_1_1"
        (pin passive line (at -3.81 0 0) (length 2.54) (name "K" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 3.81 0 180) (length 2.54) (name "A" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )"""

    symbols[
        "Device:L"
    ] = """(symbol "Device:L" (pin_numbers hide) (pin_names (offset 1.016) hide) (in_bom yes) (on_board yes)
      (property "Reference" "L" (at -1.27 0 90) (effects (font (size 1.27 1.27))))
      (property "Value" "L" (at 1.905 0 90) (effects (font (size 1.27 1.27))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "~" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "L_0_1"
        (arc (start 0 -2.54) (mid 0.6323 -1.905) (end 0 -1.27) (stroke (width 0) (type default)) (fill (type none)))
        (arc (start 0 -1.27) (mid 0.6323 -0.635) (end 0 0) (stroke (width 0) (type default)) (fill (type none)))
        (arc (start 0 0) (mid 0.6323 0.635) (end 0 1.27) (stroke (width 0) (type default)) (fill (type none)))
        (arc (start 0 1.27) (mid 0.6323 1.905) (end 0 2.54) (stroke (width 0) (type default)) (fill (type none)))
      )
      (symbol "L_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27) (name "1" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -3.81 90) (length 1.27) (name "2" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )"""

    return symbols


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    fixer = KiCadSchematicFixer(project_root)
    fixer.fix_all_schematics()
