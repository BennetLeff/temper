from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist


class DSNSchemaHasher:
    """Compute a content hash of the DSN structural skeleton and embed/parse headers."""

    @staticmethod
    def compute_schema_hash(board: Board, netlist: Netlist) -> str:
        """Compute SHA-256 hash of the DSN schema skeleton.

        Covers: layer names/types, component footprint names/pin counts,
        net names, design rules.
        Does NOT cover: positions, rotations, pin coordinates, wiring.
        """
        schema: dict = {}

        # Layers
        if board.layer_stackup:
            layer_names = sorted(ly.name for ly in board.layer_stackup.layers)
            layer_types = {ly.name: ly.layer_type for ly in board.layer_stackup.layers}
        else:
            layer_names = sorted(["F.Cu", "B.Cu"])
            layer_types = {"F.Cu": "signal", "B.Cu": "signal"}
        schema["layers"] = {
            "count": len(layer_names),
            "names": layer_names,
            "types": {n: layer_types.get(n, "signal") for n in layer_names},
        }

        # Footprints (sorted by name, pin counts)
        fp_info: dict[str, int] = {}
        for comp in netlist.components:
            fp_name = comp.footprint
            pin_count = len(comp.pins)
            fp_info[fp_name] = max(fp_info.get(fp_name, 0), pin_count)
        schema["footprints"] = dict(sorted(fp_info.items()))

        # Nets (sorted by name)
        schema["nets"] = sorted(n.name for n in netlist.nets)

        # Rules (constant for now; extendable)
        schema["rules"] = {"trace_width": 13, "clearance": 12}

        canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def embed_header(dsn_text: str, schema_hash: str) -> str:
        """Insert ;schema-version: sha256:<hash> as the first line."""
        header = f";schema-version: sha256:{schema_hash}"
        if dsn_text.startswith(";schema-version:"):
            first_nl = dsn_text.index("\n")
            return header + dsn_text[first_nl:]
        return f"{header}\n{dsn_text}"

    @staticmethod
    def extract_hash(dsn_text: str) -> str | None:
        """Extract schema-version hash from DSN header comment, or None."""
        for line in dsn_text.split("\n"):
            if line.startswith(";schema-version: sha256:"):
                return line[len(";schema-version: sha256:"):].strip()
        return None
