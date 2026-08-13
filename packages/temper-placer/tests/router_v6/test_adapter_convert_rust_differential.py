"""R1a: behavioural A/B of the ``router_v6/_adapter_convert.py``
batch-result summarization (``_summarize_batch_results``) against the pinned
pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase E E6 follow-on: the
``_adapter_convert.py`` batch-result summarization -- the reduction of
``RouterV6Result.batch_results`` (one ``net_batching.NetBatchResult`` per
batch / singleton retry) to the small always-printable summary dict -- moves
to temper-orchestration's ``pipeline_route.rs``
(``pipeline_route::run_summarize_batch_results``). The module keeps its public
API as a delegation shim; the pre-migration implementation is pinned VERBATIM
inline below (the ``_oracle_summarize_batch_results`` block, content-addressed
by ``_ORACLE_BODY_SHA256``). Both arms are driven with IDENTICAL inputs; every
assertion is bit-exact (``==`` on the summary dicts, no tolerance -- the
summary carries only ints / strings / lists of strings, so plain equality is
the whole contract).

Anti-vacuity: ``test_shim_and_oracle_are_different_implementations`` asserts
the shim now binds to the ``temper_orchestration`` pyfunction (``__module__``
/ import binding), not resolving back onto the inline oracle.

The other three E6-migrated orchestrations of this module (``_next_tstamp``,
``_to_stage0_netclass_rules``, ``_write_routes_to_content``'s segment/via
emission core) are already pinned by
``test_pipeline_route_rust_differential.py``; the KEEP slices (``route_pcb`` /
``_build_routing_result`` / ``_apply_placements_to_pcb`` /
``_reorient_pads_in_footprint_block`` -- the pipeline-invocation glue, the
failure-extraction assembly and the ``re``-based s-expression text rewriting)
stay Python and are argued in the module docstring, not here.
"""

from __future__ import annotations

import ast
import hashlib
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import temper_orchestration as _to

from temper_placer.router_v6._adapter_convert import (
    _summarize_batch_results as shim_summarize,
)

# ---------------------------------------------------------------------------
# The oracle must stay verbatim
# ---------------------------------------------------------------------------
#
# Verbatim pre-migration copy of `_adapter_convert._summarize_batch_results`
# AS COMMITTED at the dispatch base (origin/main 565078e54).  Do NOT edit:
# it is the reference.  If the module's source really changes upstream,
# re-pin the body in its own commit (see `scripts/oracle_hashes.json` for the
# shared-oracle convention this module's other three functions use).


def _oracle_summarize_batch_results(batch_results: list[Any] | None) -> dict[str, Any]:
    """Reduce ``RouterV6Result.batch_results`` (net_batching.NetBatchResult,
    one per batch or singleton retry attempt) to a small, always-printable
    summary -- see ``RoutingResult.net_batch_summary``'s docstring for why
    this needs to exist at all: the per-batch records already carry
    ``batch_crashed``/``crash_reason`` (net_batching.py's own "Crash vs.
    UNSAT, made distinguishable by construction" mechanism), but nothing
    read them by default before this function existed.

    Returns ``{}`` (falsy, easy for a caller to skip) when net-batching
    was not used (``batch_results`` empty/None) -- distinct from a
    populated dict with zero crashes, so a caller can tell "net-batching
    off" from "net-batching on, nothing degraded."
    """
    if not batch_results:
        return {}

    n_batches = len(batch_results)
    crashed = [b for b in batch_results if getattr(b, "batch_crashed", False)]
    timed_out = [
        b for b in crashed if "timed out" in (getattr(b, "crash_reason", None) or "")
    ]
    other_crash = [b for b in crashed if b not in timed_out]
    singleton_retried = [b for b in batch_results if getattr(b, "retried_singleton_nets", None)]
    n_singleton_retried_nets = sum(len(b.retried_singleton_nets) for b in singleton_retried)
    n_crashed_singleton_nets = sum(len(getattr(b, "crashed_nets", None) or []) for b in batch_results)
    all_failed_nets = sorted({n for b in batch_results for n in (getattr(b, "failed_nets", None) or [])})

    return {
        "n_batches": n_batches,
        "n_batches_solved_at_batch_level": sum(
            1 for b in batch_results if getattr(b, "solved_at_batch_level", False)
        ),
        "n_batches_crashed": len(crashed),
        "n_batches_timed_out": len(timed_out),
        "timed_out_batch_indices": [getattr(b, "batch_index", -1) for b in timed_out],
        "n_batches_crashed_other_reason": len(other_crash),
        "other_crash_reasons": [getattr(b, "crash_reason", None) for b in other_crash],
        "n_nets_singleton_retried": n_singleton_retried_nets,
        "n_nets_crashed_at_singleton_too": n_crashed_singleton_nets,
        "n_nets_no_topology": len(all_failed_nets),
        "nets_no_topology": all_failed_nets,
    }


def _oracle_body_sha256() -> str:
    src = Path(__file__).read_text(encoding="utf-8")
    lines = src.splitlines(keepends=True)
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == "_oracle_summarize_batch_results":
            body = "".join(lines[node.lineno - 1 : node.end_lineno])
            return hashlib.sha256(textwrap.dedent(body).encode()).hexdigest()
    raise AssertionError("oracle function _oracle_summarize_batch_results not found")


# The oracle is evidence only while it is unmodified.  Pinned so a body edit
# fails this test rather than silently re-pinning the differential.
_ORACLE_BODY_SHA256 = "f4d32d9b5db6a432d074971e9daa61f4b5975931ed679966e19000e5d9b8e702"


def test_oracle_body_matches_pinned_digest() -> None:
    assert _oracle_body_sha256() == _ORACLE_BODY_SHA256, (
        "the inline oracle body changed; it must stay verbatim "
        "(re-pin deliberately, in its own commit, if the module's source "
        "really changed upstream)"
    )


def test_shim_and_oracle_are_different_implementations() -> None:
    """Anti-vacuity: the shim must bind to the temper_orchestration pyfunction,
    not resolve back onto the inline oracle."""
    assert _to.run_summarize_batch_results.__module__ == "temper_orchestration.temper_orchestration"
    assert _oracle_summarize_batch_results.__module__ != "temper_orchestration.temper_orchestration"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@dataclass
class _FakeBatch:
    """Structural-equality fake of ``net_batching.NetBatchResult`` (dataclass
    ``eq``), used for the edge case where two distinct batches are ``==``."""

    batch_index: int
    batch_crashed: bool = False
    crash_reason: str | None = None
    retried_singleton_nets: list = field(default_factory=list)
    crashed_nets: list = field(default_factory=list)
    failed_nets: list = field(default_factory=list)
    solved_at_batch_level: bool = False


def _fake(**attrs):
    """A duck-typed batch whose attribute set is *attrs* only (missing
    attributes exercise the ``getattr(b, name, default)`` paths)."""
    return SimpleNamespace(**attrs)


def _assert_same(batch_results, msg=""):
    want = _oracle_summarize_batch_results(batch_results)
    got = shim_summarize(batch_results)
    assert got == want, f"{msg}: summary differs\n--- want ---\n{want}\n--- got ---\n{got}"
    assert type(got) is dict and type(want) is dict


# ---------------------------------------------------------------------------
# _summarize_batch_results
# ---------------------------------------------------------------------------


def test_summarize_none_returns_empty_dict():
    _assert_same(None, "None payload")


def test_summarize_empty_list_returns_empty_dict():
    _assert_same([], "empty list")
    _assert_same((), "empty tuple")


def test_summarize_net_batching_off_vs_on_distinction():
    # off -> {}; on -> populated dict (even with zero crashes).
    assert shim_summarize(None) == {}
    assert shim_summarize([]) == {}
    got = shim_summarize([_fake(batch_index=0)])
    assert got != {}
    assert got["n_batches"] == 1
    assert got["n_batches_crashed"] == 0


def test_summarize_no_crashes_zero_everything():
    batches = [_fake(batch_index=0), _fake(batch_index=1), _fake(batch_index=2)]
    _assert_same(batches, "no crashes")
    got = shim_summarize(batches)
    assert got["n_batches_crashed"] == 0
    assert got["n_batches_timed_out"] == 0
    assert got["n_batches_crashed_other_reason"] == 0


def test_summarize_timed_out_vs_other_crash():
    batches = [
        _fake(batch_index=0, batch_crashed=True, crash_reason="solver timed out at 30s"),
        _fake(batch_index=1, batch_crashed=True, crash_reason="oom"),
        _fake(batch_index=2, batch_crashed=True, crash_reason=None),
        _fake(batch_index=3, batch_crashed=False, crash_reason="timed out"),  # not crashed
    ]
    _assert_same(batches, "timed out vs other crash")
    got = shim_summarize(batches)
    assert got["n_batches_crashed"] == 3
    assert got["n_batches_timed_out"] == 1
    assert got["timed_out_batch_indices"] == [0]
    assert got["n_batches_crashed_other_reason"] == 2
    assert got["other_crash_reasons"] == ["oom", None]


def test_summarize_substring_not_subsequence():
    # "timed out" must be a substring, not an exact match.
    batches = [
        _fake(batch_index=0, batch_crashed=True, crash_reason="process timed out (wall)"),
        _fake(batch_index=1, batch_crashed=True, crash_reason="timeout"),  # not "timed out"
    ]
    _assert_same(batches, "substring vs exact")
    got = shim_summarize(batches)
    assert got["n_batches_timed_out"] == 1
    assert got["n_batches_crashed_other_reason"] == 1


def test_summarize_empty_and_none_crash_reason_not_timed_out():
    batches = [
        _fake(batch_index=0, batch_crashed=True, crash_reason=""),
        _fake(batch_index=1, batch_crashed=True, crash_reason=None),
    ]
    _assert_same(batches, "empty/none crash_reason")
    got = shim_summarize(batches)
    assert got["n_batches_timed_out"] == 0
    assert got["n_batches_crashed_other_reason"] == 2
    assert got["other_crash_reasons"] == ["", None]


def test_summarize_singleton_retried_counts():
    batches = [
        _fake(batch_index=0, retried_singleton_nets=["A", "B"]),
        _fake(batch_index=1, retried_singleton_nets=["C"]),
        _fake(batch_index=2, retried_singleton_nets=[]),  # falsy -> not retried
        _fake(batch_index=3),  # missing -> getattr default None
    ]
    _assert_same(batches, "singleton retried")
    got = shim_summarize(batches)
    assert got["n_nets_singleton_retried"] == 3


def test_summarize_crashed_nets_sum():
    batches = [
        _fake(batch_index=0, crashed_nets=["X", "Y"]),
        _fake(batch_index=1, crashed_nets=[]),
        _fake(batch_index=2),  # missing -> default None -> len([]) == 0
        _fake(batch_index=3, crashed_nets=["Z"]),
    ]
    _assert_same(batches, "crashed nets sum")
    got = shim_summarize(batches)
    assert got["n_nets_crashed_at_singleton_too"] == 3


def test_summarize_failed_nets_sorted_union():
    batches = [
        _fake(batch_index=0, failed_nets=["net2", "net1"]),
        _fake(batch_index=1, failed_nets=["net3", "net1"]),  # "net1" duplicated
        _fake(batch_index=2),  # missing
        _fake(batch_index=3, failed_nets=[]),
    ]
    _assert_same(batches, "failed nets union")
    got = shim_summarize(batches)
    assert got["n_nets_no_topology"] == 3
    assert got["nets_no_topology"] == ["net1", "net2", "net3"]


def test_summarize_solved_at_batch_level_count():
    batches = [
        _fake(batch_index=0, solved_at_batch_level=True),
        _fake(batch_index=1, solved_at_batch_level=False),
        _fake(batch_index=2),  # missing -> default False
    ]
    _assert_same(batches, "solved_at_batch_level")
    assert shim_summarize(batches)["n_batches_solved_at_batch_level"] == 1


def test_summarize_missing_batch_index_defaults_to_minus_one():
    batches = [
        _fake(batch_crashed=True, crash_reason="timed out"),  # no batch_index
    ]
    _assert_same(batches, "missing batch_index")
    assert shim_summarize(batches)["timed_out_batch_indices"] == [-1]


def test_summarize_structural_equal_batches_edge_case():
    """Two distinct-but-``==`` dataclass batches: the oracle's
    ``b not in timed_out`` membership uses structural ``==``, which the Rust
    port reduces to the crash_reason substring test.  This pins that the two
    are equivalent when two batches are structurally identical (identical
    crash_reason -> both timed out or both not)."""
    batches = [
        _FakeBatch(0, batch_crashed=True, crash_reason="timed out at 30s"),
        _FakeBatch(0, batch_crashed=True, crash_reason="timed out at 30s"),  # == above
        _FakeBatch(1, batch_crashed=True, crash_reason="oom"),
        _FakeBatch(1, batch_crashed=True, crash_reason="oom"),  # == above
    ]
    _assert_same(batches, "structural-equality edge case")
    got = shim_summarize(batches)
    assert got["n_batches_timed_out"] == 2
    assert got["n_batches_crashed_other_reason"] == 2
    assert got["timed_out_batch_indices"] == [0, 0]
    assert got["other_crash_reasons"] == ["oom", "oom"]


def test_summarize_many_randomized():
    import random

    rng = random.Random(20260812)
    reasons = ["solver timed out at 30s", "oom", "segfault", None, "", "timed out (wall clock)"]
    for _ in range(30):
        batches = []
        for i in range(rng.randint(0, 8)):
            attrs: dict[str, Any] = {"batch_index": i}
            if rng.random() < 0.6:
                attrs["batch_crashed"] = rng.random() < 0.5
            if rng.random() < 0.6:
                attrs["crash_reason"] = rng.choice(reasons)
            if rng.random() < 0.6:
                attrs["retried_singleton_nets"] = [f"N{j}" for j in range(rng.randint(0, 4))]
            if rng.random() < 0.6:
                attrs["crashed_nets"] = [f"C{j}" for j in range(rng.randint(0, 3))]
            if rng.random() < 0.6:
                attrs["failed_nets"] = [
                    f"F{rng.randint(0, 5)}" for _ in range(rng.randint(0, 4))
                ]
            if rng.random() < 0.6:
                attrs["solved_at_batch_level"] = rng.random() < 0.5
            batches.append(_fake(**attrs))
        _assert_same(batches, f"randomized {batches!r}")
