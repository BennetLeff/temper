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
        schema: dict = {}
        if board.layer_stackup:
            layer_names = sorted(l.name for l in board.layer_stackup.layers)
            layer_types = {l.name: l.layer_type for l in board.layer_stackup.layers}
        else:
            layer_names = sorted(["F.Cu", "B.Cu"])
            layer_types = {"F.Cu": "signal", "B.Cu": "signal"}
        schema["layers"] = {
            "count": len(layer_names),
            "names": layer_names,
            "types": {n: layer_types.get(n, "signal") for n in layer_names},
        }
        fp_info: dict[str, int] = {}
        for comp in netlist.components:
            fp_info[comp.footprint] = max(fp_info.get(comp.footprint, 0), len(comp.pins))
        schema["footprints"] = dict(sorted(fp_info.items()))
        schema["nets"] = sorted(n.name for n in netlist.nets)
        schema["rules"] = {"trace_width": 13, "clearance": 12}
        canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def embed_header(dsn_text: str, schema_hash: str) -> str:
        header = f";schema-version: sha256:{schema_hash}"
        if dsn_text.startswith(";schema-version:"):
            first_nl = dsn_text.index("\n")
            return header + dsn_text[first_nl:]
        return f"{header}\n{dsn_text}"

    @staticmethod
    def extract_hash(dsn_text: str) -> str | None:
        for line in dsn_text.split("\n"):
            if line.startswith(";schema-version: sha256:"):
                return line[len(";schema-version: sha256:"):].strip()
        return None
