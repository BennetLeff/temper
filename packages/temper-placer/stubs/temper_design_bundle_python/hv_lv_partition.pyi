"""Type stubs for `temper_design_bundle_python.hv_lv_partition`.

Compiled from `packages/temper-design-bundle/src/hv_lv_partition.rs` -- the
Wave-4 migration of `deterministic/stages/hv_lv_partition.py`'s guard-strip
classification/area-decision kernels. Keep in sync with that file.
"""

from __future__ import annotations

from typing import Any


def hv_lv_classify(
    *args: Any,
    **kwargs: Any,
) -> tuple[Any, Any, Any, Any, Any, Any]: ...
def hv_lv_area_check(
    *args: Any,
    **kwargs: Any,
) -> tuple[Any, Any, Any, Any, Any]: ...
