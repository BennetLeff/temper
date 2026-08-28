from __future__ import annotations

import json
import math

import pytest

from temper_placer.placer.cp_sat.creepage_cut_replay import (
    SCHEMA_NAME,
    decode_creepage_cut_replay,
    encode_creepage_cut_replay,
)


def test_canonical_max_reduction_and_identity() -> None:
    text = encode_creepage_cut_replay(
        [("U2", "K1", 2.0), ("K1", "U2", 4.5)],
        board_identity="board",
        input_identity="input",
    )
    assert decode_creepage_cut_replay(
        text, expected_board_identity="board", expected_input_identity="input"
    ) == (("K1", "U2", 4.5),)


@pytest.mark.parametrize(
    "cut", [("A", "A", 1.0), ("A", "B", -1.0), ("A", "B", math.inf), (" A", "B", 1.0), ("A", "B", True)]
)
def test_invalid_cuts_rejected(cut: tuple[object, object, object]) -> None:
    with pytest.raises(ValueError):
        encode_creepage_cut_replay([cut])


def test_schema_rejects_unknown_and_nonfinite_values() -> None:
    with pytest.raises(ValueError):
        decode_creepage_cut_replay(json.dumps({"schema": SCHEMA_NAME, "version": 1, "cuts": [], "extra": 1}))
    with pytest.raises(ValueError, match="non-finite"):
        decode_creepage_cut_replay('{"schema":"temper.creepage_cut_replay","version":1,"cuts":[],"board_identity":NaN}')
