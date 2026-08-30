"""Tests for check_erc_off_grid_consequence.py.

Reproduces and pins the fix for finding 1 of
docs/evidence/2026-08-11-gate-vacuity-audit.md: an ``endpoint_off_grid``
pin with no atopile-compiled net at all (``NO_ATOPILE_NET``) used to be
folded into the same unqualified "PASSED" verdict as a pin that was
actually checked and matched member-for-member. A pin this gate
structurally cannot verify is not evidence the pin is safe, so it must
fail the gate (exit 1) rather than pass silently.

These deliberately do NOT rely on kicad-cli or the real board (matching
the pattern used by scripts/tests/test_check_domain_partition.py):
every scenario here builds small, hand-written synthetic ERC JSON /
schematic netlist XML / atopile netlist / domain manifest inputs, and
invokes the real, unmodified script as a subprocess -- the same
black-box invocation CI uses (.github/workflows/python-tests.yml,
"ERC endpoint_off_grid consequence gate").
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "check_erc_off_grid_consequence.py"


def _write_erc_json(path: Path, entries: list[tuple[str, str]]) -> None:
    """entries: [(ref, pin), ...] each becomes one endpoint_off_grid violation."""
    path.write_text(
        json.dumps(
            {
                "sheets": [
                    {
                        "violations": [
                            {
                                "type": "endpoint_off_grid",
                                "items": [{"description": f"Symbol {ref} Pin {pin}"}],
                            }
                            for ref, pin in entries
                        ]
                    }
                ]
            }
        )
    )


def _write_sch_netlist(path: Path, nets: dict[str, list[tuple[str, str]]]) -> None:
    nets_xml = "".join(
        f'<net name="{name}">'
        + "".join(f'<node ref="{ref}" pin="{pin}"/>' for ref, pin in members)
        + "</net>"
        for name, members in nets.items()
    )
    path.write_text(f"<?xml version='1.0'?><export><nets>{nets_xml}</nets></export>")


def _write_atopile_net(path: Path, nets: dict[str, list[tuple[str, str]]]) -> None:
    net_blocks = "".join(
        f'(net (code {i}) (name "{name}")'
        + "".join(f"(node (ref {ref}) (pin {pin}))" for ref, pin in members)
        + ")"
        for i, (name, members) in enumerate(nets.items(), start=1)
    )
    path.write_text(f"(export (nets {net_blocks}))")


def _write_domain_manifest(path: Path, hv_nets: list[str], selv_nets: list[str]) -> None:
    lines = ["domains:", "  HV:", "    nets:"]
    lines += [f"      - {n}" for n in hv_nets]
    lines += ["  SELV:", "    nets:"]
    lines += [f"      - {n}" for n in selv_nets]
    path.write_text("\n".join(lines) + "\n")


def _run(tmp_path: Path, erc_json: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--erc-json",
            str(erc_json),
            "--sch-netlist-xml",
            str(tmp_path / "sch_netlist.xml"),
            "--atopile-net",
            str(tmp_path / "atopile.net"),
            "--domain-manifest",
            str(tmp_path / "domain_manifest.yaml"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_no_atopile_net_fails(tmp_path):
    """Finding 1's motivating condition: an endpoint_off_grid pin (U99 pin 1)
    sits on a live HV net in the schematic (HV_LINE, shared with J1 pin 1)
    but the atopile-compiled netlist -- the design's stated intent -- never
    declares it at all. Pre-fix this scored an unqualified exit-0 "PASSED".
    Post-fix it must fail (exit 1) and name NO_ATOPILE_NET / UNVERIFIABLE
    explicitly, distinct from a MISMATCH.
    """
    erc_json = tmp_path / "erc.json"
    _write_erc_json(erc_json, [("J1", "1"), ("U99", "1")])
    _write_sch_netlist(tmp_path / "sch_netlist.xml", {"HV_LINE": [("J1", "1"), ("U99", "1")]})
    # atopile only knows about J1 -- U99 is entirely absent from the
    # compiled design.
    _write_atopile_net(tmp_path / "atopile.net", {"HV_LINE": [("J1", "1")]})
    _write_domain_manifest(tmp_path / "domain_manifest.yaml", ["HV_LINE"], ["LV_CTRL"])

    result = _run(tmp_path, erc_json)

    assert result.returncode == 1, (
        f"expected exit 1 (FAILED) on a NO_ATOPILE_NET pin, got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "NO_ATOPILE_NET" in result.stdout
    assert "UNVERIFIABLE" in result.stdout
    assert "PASSED" not in result.stdout
    # "non-backlogged" since #1499: the gate now partitions mismatches into
    # backlogged (documented open questions, reported but not failing) and
    # non-backlogged (still failing). This assertion pins the FAILING count,
    # which is what "it's the UNVERIFIABLE class, not MISMATCH" means here.
    assert "0 non-backlogged mismatch" in result.stdout


def test_all_declared_and_matching_passes(tmp_path):
    """Legitimate current-shape input: every endpoint_off_grid pin has an
    atopile net AND the schematic net matches it member-for-member. Must
    still pass (exit 0) after the fix -- the fix must not regress the
    checked, verified case.
    """
    erc_json = tmp_path / "erc.json"
    _write_erc_json(erc_json, [("J1", "1"), ("U99", "1")])
    _write_sch_netlist(tmp_path / "sch_netlist.xml", {"HV_LINE": [("J1", "1"), ("U99", "1")]})
    _write_atopile_net(tmp_path / "atopile.net", {"HV_LINE": [("J1", "1"), ("U99", "1")]})
    _write_domain_manifest(tmp_path / "domain_manifest.yaml", ["HV_LINE"], ["LV_CTRL"])

    result = _run(tmp_path, erc_json)

    assert result.returncode == 0, (
        f"expected exit 0 (PASSED) when every pin is declared and matches, "
        f"got {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "PASSED" in result.stdout
    assert "NO_ATOPILE_NET" not in result.stdout


def test_mismatch_still_fails(tmp_path):
    """Pre-existing behavior, unchanged by the fix: a pin declared in
    atopile but sitting on a schematic net that diverges from it is a
    MISMATCH and must still fail."""
    erc_json = tmp_path / "erc.json"
    _write_erc_json(erc_json, [("J1", "1")])
    # Schematic puts J1 pin 1 on a net named differently from what atopile
    # declares for that pin -- a genuine member-set divergence.
    _write_sch_netlist(tmp_path / "sch_netlist.xml", {"WRONG_NET": [("J1", "1")]})
    _write_atopile_net(tmp_path / "atopile.net", {"HV_LINE": [("J1", "1")]})
    _write_domain_manifest(tmp_path / "domain_manifest.yaml", ["HV_LINE"], ["LV_CTRL"])

    result = _run(tmp_path, erc_json)

    assert result.returncode == 1
    assert "MISMATCH" in result.stdout
    assert "0 unverifiable" in result.stdout  # confirms it's the MISMATCH class, not NO_ATOPILE_NET


def test_mixed_mismatch_and_no_atopile_net_reports_both(tmp_path):
    """Both failure classes can fire in the same run and must both be
    counted and named in the FAILED summary."""
    erc_json = tmp_path / "erc.json"
    _write_erc_json(erc_json, [("J1", "1"), ("U99", "1")])
    _write_sch_netlist(
        tmp_path / "sch_netlist.xml",
        {"WRONG_NET": [("J1", "1")], "HV_LINE": [("U99", "1")]},
    )
    _write_atopile_net(tmp_path / "atopile.net", {"HV_LINE": [("J1", "1")]})
    _write_domain_manifest(tmp_path / "domain_manifest.yaml", ["HV_LINE"], ["LV_CTRL"])

    result = _run(tmp_path, erc_json)

    assert result.returncode == 1
    assert "1 non-backlogged mismatch" in result.stdout  # see note in test_no_atopile_net_fails
    assert "1 unverifiable" in result.stdout
