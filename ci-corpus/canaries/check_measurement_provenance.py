"""Canary fixtures for check_measurement_provenance.py (R42).

Uses ``evaluate()`` directly (already split from I/O for exactly this kind
of direct unit-testing -- see its own docstring) against a synthetic
artifact and an empty allowlist, so no git commit needs to actually exist:
``measured_at_commit`` is left as ``"UNKNOWN"``, which the gate treats as
"no commit to verify" rather than attempting real git resolution.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def _artifact(root: Path, *, board_content: bytes, recorded_sha: str) -> Path:
    board = root / "board.bin"
    board.write_bytes(board_content)
    artifact = root / "measurement.json"
    artifact.write_text(
        json.dumps(
            {
                "error_ceiling": 100,
                "provenance": {
                    "measured_at_commit": "UNKNOWN",
                    "dirty": False,
                    "source": "measured-live",
                    "inputs": [{"path": "board.bin", "sha256": recorded_sha}],
                },
            }
        ),
        encoding="utf-8",
    )
    return artifact


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _state(gate_module, root: Path, artifact: Path) -> str:
    try:
        outcome = gate_module.evaluate(root, [artifact], {})
    except gate_module.GateError:
        return "error"
    if outcome.problems or outcome.stale:
        return "violation"
    return "clean"


def pristine_fresh(gate_module) -> str:
    """The recorded input hash matches the board file's real, current
    content -- fresh, must PASS."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        content = b"board-content-v1"
        artifact = _artifact(root, board_content=content, recorded_sha=_sha256(content))
        return _state(gate_module, root, artifact)


def seed_stale_input(gate_module) -> str:
    """The board file on disk has moved since the recorded hash was taken
    -- the real drc_ceiling.json incident (91 vs ~710 errors) this gate
    exists to catch."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        current_content = b"board-content-v2-CHANGED"
        stale_recorded_sha = _sha256(b"board-content-v1")
        artifact = _artifact(root, board_content=current_content, recorded_sha=stale_recorded_sha)
        return _state(gate_module, root, artifact)


def seed_zero_artifacts(gate_module) -> str:
    """No measurement artifacts registered at all -- the anti-vacuous-truth
    case: `evaluate()` must fail closed (GateError), never report a clean
    pass for a scan that checked nothing.

    ``evaluate()`` actually carries TWO overlapping fail-closed guards for
    this exact input shape: `if not artifacts: raise ...` fires first, and
    -- because an empty ``artifacts`` list can never make the per-record
    loop increment ``total_records`` -- `if total_records == 0: raise ...`
    would ALSO fire for this same input if the first guard were the only
    one stripped. A coarse "did it raise at all" oracle cannot tell those
    two guards apart (both raise GateError -- "error" either way), so this
    checks the raised message specifically: the two guards' messages are
    deliberately distinct ("zero measurement artifacts registered" vs
    "zero provenance-bearing records found"), and only the message names
    which check actually fired.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        try:
            gate_module.evaluate(root, [], {})
            return "clean"
        except gate_module.GateError as exc:
            if "zero measurement artifacts registered" in str(exc):
                return "error:zero-artifacts"
            return f"error:other:{exc}"
