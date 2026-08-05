"""Differential test: prereg temporal gate in Rust
(temper_design_bundle_python.validation) vs the pinned Python oracle
(Wave 4, Phase 4 — validation remainder slice).

``temper_placer/validation/prereg/schema.py`` is a pydantic schema; per the
config-loader precedent (Phase 3 candidate 5) pydantic is NOT reimplemented
in Rust — the models and their ``model_validator`` call-backs stay Python,
as does ``_parse_iso_to_utc`` (``datetime.fromisoformat`` is a Python
library semantic whose error text must stay CPython's, and the function is
imported directly by the out-of-scope ``helps_battery.py``). What moves is
the temporal-gate CONTROL FLOW in ``PreregistrationManifest.load`` — the
naive-to-UTC normalization decision, the ``created > battery`` comparison
(via Python's own ``>`` operator, called back), and the ValueError
construction — to the ``validation`` submodule of
``temper_design_bundle_python``. yaml.safe_load and
``PreregistrationManifest.model_validate`` stay in the shim (the
candidate-5 call-backs).

Comparison convention: outcome equivalence — either both arms load
successfully, or both raise a ValueError whose message is byte-identical
(``str(exc)``).

Sections:
- Differential bit-exactness (gate outcomes + error strings).
- PBT (hypothesis): five non-vacuous properties.
- Metamorphic relations: three, honestly bounded.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

import tests.validation.prereg._schema_py_oracle as _oracle
from temper_placer.validation.prereg.schema import (
    PreregistrationManifest as ShimManifest,
)

# Rust symbol under test — must exist or this file fails to collect (RED).
PREREG_TEMPORAL_GATE = _tdb.validation.prereg_temporal_gate

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _manifest_yaml(created_at: str) -> str:
    """A minimal but schema-valid pre-registration manifest with the given
    created_at."""
    return (
        "version: 1\n"
        f"created_at: {created_at}\n"
        "fields:\n"
        "  - field_name: thermal\n"
        "    independent_instrument: temper_placer.physics.thermal.ThermalOracle\n"
        "    cheap_baseline:\n"
        "      name: uniform_heat_spread\n"
        "      description: No thermal optimization.\n"
        "      metric: thermal_score\n"
        "      target_value: 0.0\n"
        "      because: Worst-case thermal profile.\n"
        "    parametric_ranges:\n"
        "      - parameter: max_heatspread_mm\n"
        "        min: 5.0\n"
        "        max: 40.0\n"
        "        because: Tight enclosure to open chassis.\n"
        "    structural_bounding_cases:\n"
        "      - case_name: single_igbt\n"
        "        description: Single IGBT, passive cooling.\n"
        "        because: Minimum viable configuration.\n"
        "    pass_bar:\n"
        "      margin_gain: {name: X, value: 0.10, because: Must improve.}\n"
        "      beat_cheap_baseline_by: {name: Y, value: 0.05, because: Must beat.}\n"
        "      across_perturbations: {name: N, value: 5.0, because: Minimum 5.}\n"
        "    kill_criterion:\n"
        "      description: The condition that kills a field.\n"
        "      because: Auditable rationale.\n"
        "    cost_budget:\n"
        "      max_total_battery_seconds: 3600.0\n"
        "      max_rounds_budget: 10\n"
        "      field_convergence_round_limit: 5\n"
        "      thermal_grid_cells_max: 64\n"
        "      target_solve_time_ms_per_field: 120000.0\n"
    )


def _write_manifest(tmp_path: Path, created_at: str) -> Path:
    p = tmp_path / "prereg.yaml"
    p.write_text(_manifest_yaml(created_at), encoding="utf-8")
    return p


def _run_gate_both(path: Path, battery: datetime | None):
    if battery is None:
        return (
            _oracle.PreregistrationManifest.load(path),
            ShimManifest.load(path),
        )
    try:
        o = _oracle.PreregistrationManifest.load(path, battery)
        o_err = None
    except ValueError as e:
        o, o_err = None, str(e)
    try:
        s = ShimManifest.load(path, battery)
        s_err = None
    except ValueError as e:
        s, s_err = None, str(e)
    assert (o_err is None) == (s_err is None)
    if o_err is not None:
        return o_err, s_err
    assert o is not None and s is not None
    return (o.version, o.created_at, len(o.fields)), (s.version, s.created_at, len(s.fields))


# ---------------------------------------------------------------------------
# Differential — gate outcomes and error strings
# ---------------------------------------------------------------------------

_ISO = st.datetimes(
    min_value=datetime(2020, 1, 1, tzinfo=UTC),
    max_value=datetime(2030, 1, 1, tzinfo=UTC),
)


@settings(max_examples=60, deadline=None)
@given(_ISO, _ISO)
def test_gate_differential_random(created, battery):
    """Random aware-UTC pairs: both arms agree on accept/reject and, when
    rejected, on the byte-identical ValueError."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write_manifest(Path(td), created.isoformat())
        o, s = _run_gate_both(path, battery)
        if isinstance(o, str):
            assert s == o
        else:
            assert s == o


def test_gate_differential_hand_built():
    import tempfile

    base = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Exact same timestamp -> accepted.
        path = _write_manifest(td, base.isoformat())
        o, s = _run_gate_both(path, base)
        assert o == s and not isinstance(o, str)

        # Future created_at -> rejected with identical message.
        future = (base + timedelta(days=1)).isoformat()
        path = _write_manifest(td, future)
        o, s = _run_gate_both(path, base)
        assert isinstance(o, str) and s == o
        assert "post-dates battery-run timestamp" in o

        # Past created_at -> accepted.
        past = (base - timedelta(days=1)).isoformat()
        path = _write_manifest(td, past)
        o, s = _run_gate_both(path, base)
        assert o == s and not isinstance(o, str)

        # Naive battery timestamp treated as UTC.
        path = _write_manifest(td, base.isoformat())
        naive_future = base.replace(tzinfo=None) - timedelta(hours=1)
        o, s = _run_gate_both(path, naive_future)
        assert o == s and not isinstance(o, str)
        # Naive battery that is "later" in wall time but earlier in UTC.
        naive_later_wall = base.replace(tzinfo=None) + timedelta(hours=2)
        path = _write_manifest(td, (base - timedelta(hours=1)).isoformat())
        o, s = _run_gate_both(path, naive_later_wall)
        assert o == s and not isinstance(o, str)

        # Different UTC offsets: created at +02:00, battery UTC.
        path = _write_manifest(td, (base + timedelta(hours=2)).isoformat().replace("+00:00", "+02:00"))
        o, s = _run_gate_both(path, base)
        assert o == s and not isinstance(o, str)  # same instant

        # No battery timestamp -> gate skipped.
        path = _write_manifest(td, (base + timedelta(days=30)).isoformat())
        o, s = _run_gate_both(path, None)
        assert o == s and not isinstance(o, str)

        # 'Z' suffix created_at (the _parse_iso_to_utc Z->+00:00 branch).
        path = _write_manifest(td, (base + timedelta(days=1)).isoformat().replace("+00:00", "Z"))
        o, s = _run_gate_both(path, base)
        assert isinstance(o, str) and s == o


def test_pydantic_validation_still_enforced_through_the_shim():
    """The schema validation call-backs are untouched: a malformed record
    still raises pydantic ValidationError through the shim, byte-identically
    to the oracle."""
    import tempfile

    bad = (
        "version: 1\n"
        "created_at: 2026-01-01T00:00:00+00:00\n"
        "fields:\n"
        "  - field_name: thermal\n"
        "    independent_instrument: x\n"
        "    cheap_baseline: {name: a, description: b, metric: m, target_value: 0.0}\n"
        "    parametric_ranges: []\n"
        "    structural_bounding_cases: []\n"  # must not be empty
        "    pass_bar:\n"
        "      margin_gain: {name: X, value: 0.1}\n"  # missing because
        "      beat_cheap_baseline_by: {name: Y, value: 0.05}\n"
        "      across_perturbations: {name: N, value: 5.0}\n"
        "    kill_criterion: {description: d}\n"
        "    cost_budget:\n"
        "      max_total_battery_seconds: 1.0\n"
        "      max_rounds_budget: 1\n"
        "      field_convergence_round_limit: 1\n"
        "      thermal_grid_cells_max: 1\n"
        "      target_solve_time_ms_per_field: 1.0\n"
    )
    from pydantic import ValidationError

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bad.yaml"
        path.write_text(bad, encoding="utf-8")
        with pytest.raises(ValidationError) as o_exc:
            _oracle.PreregistrationManifest.load(path)
        with pytest.raises(ValidationError) as s_exc:
            ShimManifest.load(path)
        assert str(s_exc.value) == str(o_exc.value)


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties (R1c)
# ---------------------------------------------------------------------------


@settings(max_examples=40, deadline=None)
@given(_ISO)
def test_prop1_gate_accepts_created_at_strictly_before_battery(created):
    import tempfile

    battery = created + timedelta(days=1)
    with tempfile.TemporaryDirectory() as td:
        path = _write_manifest(Path(td), created.isoformat())
        result = ShimManifest.load(path, battery)
        assert result.created_at == created.isoformat()


@settings(max_examples=40, deadline=None)
@given(_ISO)
def test_prop2_gate_accepts_created_at_equal_to_battery(created):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = _write_manifest(Path(td), created.isoformat())
        result = ShimManifest.load(path, created)
        assert result.created_at == created.isoformat()


@settings(max_examples=40, deadline=None)
@given(_ISO)
def test_prop3_gate_rejects_created_at_strictly_after_battery(created):
    import tempfile

    battery = created - timedelta(days=1)
    with tempfile.TemporaryDirectory() as td:
        path = _write_manifest(Path(td), created.isoformat())
        with pytest.raises(ValueError, match="post-dates battery-run timestamp"):
            ShimManifest.load(path, battery)


def test_prop4_no_battery_timestamp_skips_the_gate_entirely():
    import tempfile

    far_future = datetime(2099, 1, 1, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as td:
        path = _write_manifest(Path(td), far_future.isoformat())
        result = ShimManifest.load(path)
        assert result.created_at == far_future.isoformat()


@settings(max_examples=40, deadline=None)
@given(_ISO)
def test_prop5_naive_battery_is_treated_as_utc(created):
    """A naive battery timestamp is interpreted as UTC (the oracle's
    ``replace(tzinfo=UTC)`` normalization)."""
    import tempfile

    naive = created.replace(tzinfo=None) - timedelta(hours=1)
    with tempfile.TemporaryDirectory() as td:
        path = _write_manifest(Path(td), created.isoformat())
        # created == battery_utc + 1h, so created > battery -> reject.
        with pytest.raises(ValueError, match="post-dates"):
            ShimManifest.load(path, naive)


# ---------------------------------------------------------------------------
# Metamorphic relations (R1d)
# ---------------------------------------------------------------------------


def test_mr1_translating_both_timestamps_preserves_the_outcome():
    """Shifting both created_at and battery by the same timedelta preserves
    accept/reject (datetime comparison is translation-invariant)."""
    import tempfile

    base_created = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    base_battery = datetime(2026, 6, 1, 13, 0, 0, tzinfo=UTC)
    outcomes = []
    for shift in [timedelta(0), timedelta(days=30), timedelta(days=-30)]:
        with tempfile.TemporaryDirectory() as td:
            path = _write_manifest(Path(td), (base_created + shift).isoformat())
            try:
                ShimManifest.load(path, base_battery + shift)
                outcomes.append("accept")
            except ValueError:
                outcomes.append("reject")
    assert outcomes == ["accept", "accept", "accept"]


def test_mr2_rejecting_by_a_larger_margin_preserves_rejection():
    """If created_at already post-dates battery, pushing battery further
    into the past preserves rejection (monotone in the battery side)."""
    import tempfile

    created = datetime(2026, 6, 2, tzinfo=UTC)
    for battery in [datetime(2026, 6, 1, tzinfo=UTC), datetime(2026, 5, 1, tzinfo=UTC)]:
        with tempfile.TemporaryDirectory() as td:
            path = _write_manifest(Path(td), created.isoformat())
            with pytest.raises(ValueError):
                ShimManifest.load(path, battery)


def test_mr3_offset_shifting_both_sides_is_identity_for_aware_pairs():
    """Adding the same fixed UTC offset delta to both aware timestamps
    preserves the outcome (comparison is on instants)."""
    import tempfile

    created = datetime(2026, 6, 2, 12, 0, 0, tzinfo=UTC)
    battery = datetime(2026, 6, 2, 13, 0, 0, tzinfo=UTC)
    outcomes = []
    for off in [0, 5, -11]:
        tz = timezone(timedelta(hours=off))
        c2 = created.astimezone(tz)
        b2 = battery.astimezone(tz)
        with tempfile.TemporaryDirectory() as td:
            path = _write_manifest(Path(td), c2.isoformat())
            try:
                ShimManifest.load(path, b2)
                outcomes.append("accept")
            except ValueError:
                outcomes.append("reject")
    assert outcomes == ["accept", "accept", "accept"]
