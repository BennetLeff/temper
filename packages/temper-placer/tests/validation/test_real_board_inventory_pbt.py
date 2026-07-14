"""Property tests for the provenance-carrying generated-board inventory."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.validation.real_board_inventory import InventoryError, build_inventory

_IDENTIFIER = st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,7}", fullmatch=True)


def _netlist(
    refs: list[str],
    net_codes: list[str],
    *,
    duplicate_ref: bool = False,
    duplicate_net_code: bool = False,
) -> str:
    components = []
    for index, ref in enumerate(refs):
        actual_ref = refs[0] if duplicate_ref and index == len(refs) - 1 else ref
        components.append(
            f"(comp (ref {actual_ref}) (value V{index}) "
            f"(footprint F{index}) (tstamps T{index}))"
        )
    nets = [
        f"(net (code {net_codes[0] if duplicate_net_code and index else code}) (name N{index}))"
        for index, code in enumerate(net_codes)
    ]
    return "(export (components " + " ".join(components) + ") (nets " + " ".join(nets) + "))"


def _write_fresh_fixture(tmp_path: Path, text: str) -> tuple[Path, Path]:
    source_root = tmp_path / "src"
    source_root.mkdir()
    source = source_root / "main.ato"
    source.write_text("module Fixture: pass\n", encoding="utf-8")
    netlist = tmp_path / "board.net"
    netlist.write_text(text, encoding="utf-8")

    # Keep the test independent of filesystem timestamp resolution.  The
    # inventory gate must see the generated artifact as newer than its source.
    os.utime(source, ns=(1, 1))
    os.utime(netlist, ns=(2, 2))
    return netlist, source_root


@pytest.mark.property
@given(
    refs=st.lists(_IDENTIFIER, min_size=1, max_size=8, unique=True),
    net_codes=st.lists(_IDENTIFIER, min_size=1, max_size=8, unique=True),
)
@settings(max_examples=100, deadline=10_000)
def test_generated_inventory_round_trips_unique_identities(
    refs: list[str],
    net_codes: list[str],
) -> None:
    """Every valid unique fixture is accepted with exact counts and hashes."""

    with tempfile.TemporaryDirectory() as temp_dir:
        netlist, source_root = _write_fresh_fixture(Path(temp_dir), _netlist(refs, net_codes))
        inventory = build_inventory(
            netlist,
            source_root=source_root,
            expected_counts=(len(refs), len(net_codes)),
        )

        assert [item["ref"] for item in inventory.components] == refs
        assert [item["code"] for item in inventory.nets] == net_codes
        assert inventory.artifact["sha256"] == hashlib.sha256(netlist.read_bytes()).hexdigest()
        assert inventory.as_dict() == build_inventory(
            netlist,
            source_root=source_root,
            expected_counts=(len(refs), len(net_codes)),
        ).as_dict()


@pytest.mark.property
@given(
    refs=st.lists(_IDENTIFIER, min_size=1, max_size=8, unique=True),
    net_codes=st.lists(_IDENTIFIER, min_size=1, max_size=8, unique=True),
)
@settings(max_examples=100, deadline=10_000)
def test_duplicate_component_identity_is_always_rejected(
    refs: list[str],
    net_codes: list[str],
) -> None:
    """A repeated reference must never silently enter the board inventory."""

    # A one-element list would otherwise duplicate the only record in place;
    # add a distinct generated ref so the malformed fixture has two components.
    if len(refs) == 1:
        refs = [refs[0], refs[0] + "X"]
    with tempfile.TemporaryDirectory() as temp_dir:
        netlist, source_root = _write_fresh_fixture(
            Path(temp_dir),
            _netlist(refs, net_codes, duplicate_ref=True),
        )
        with pytest.raises(InventoryError, match="duplicate component identity"):
            build_inventory(netlist, source_root=source_root)


@pytest.mark.property
@given(
    refs=st.lists(_IDENTIFIER, min_size=1, max_size=8, unique=True),
    net_codes=st.lists(_IDENTIFIER, min_size=2, max_size=8, unique=True),
)
@settings(max_examples=100, deadline=10_000)
def test_duplicate_net_code_is_always_rejected(
    refs: list[str],
    net_codes: list[str],
) -> None:
    """A repeated net code cannot be mistaken for two distinct nets."""

    with tempfile.TemporaryDirectory() as temp_dir:
        netlist, source_root = _write_fresh_fixture(
            Path(temp_dir),
            _netlist(refs, net_codes, duplicate_net_code=True),
        )
        with pytest.raises(InventoryError, match="duplicate net code"):
            build_inventory(netlist, source_root=source_root)
