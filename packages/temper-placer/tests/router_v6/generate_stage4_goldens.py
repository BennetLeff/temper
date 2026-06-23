"""
Generate golden fixture JSON files for Router V6 Stage 4 micro-stages.

Usage:
    uv run python packages/temper-placer/tests/router_v6/generate_stage4_goldens.py --regenerate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE.parent / "fixtures" / "stage4_goldens"


class GoldenEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if hasattr(obj, "__dataclass_fields__"):
            result = {}
            for f_name in obj.__dataclass_fields__:
                result[f_name] = self._encode_field(getattr(obj, f_name))
            return result
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        return super().default(obj)

    def _encode_field(self, val):
        if val is None:
            return None
        if isinstance(val, dict):
            return {k: self._encode_field(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [self._encode_field(v) for v in val]
        if isinstance(val, np.floating):
            return float(val)
        if isinstance(val, np.integer):
            return int(val)
        if isinstance(val, (set, frozenset)):
            return [self._encode_field(v) for v in val]
        if hasattr(val, "__dataclass_fields__"):
            result = {}
            for f_name in val.__dataclass_fields__:
                result[f_name] = self._encode_field(getattr(val, f_name))
            return result
        return val


def generate_goldens(regenerate: bool = False):
    """Generate golden fixtures by running the benchmark on each test board."""
    from temper_placer.router_v6.benchmark import run_v6_router

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for stage in ("GridPrep", "NetPrep", "Route", "ResultAggregate"):
        (GOLDEN_DIR / stage).mkdir(parents=True, exist_ok=True)

    print(f"Golden fixtures directory: {GOLDEN_DIR}")
    print("To generate live fixtures: run the pipeline on each test board")
    print("and save micro-stage outputs as JSON.")
    print()
    print("Placeholder directories created:")
    for stage in ("GridPrep", "NetPrep", "Route", "ResultAggregate"):
        print(f"  tests/fixtures/stage4_goldens/{stage}/")


if __name__ == "__main__":
    generate_goldens(regenerate="--regenerate" in sys.argv)
