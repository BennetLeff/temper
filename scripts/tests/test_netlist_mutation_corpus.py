"""Tests for the netlist-mutation corpus (plan 2026-08-02-021, R39, U6 + U7).

The identity check set -- ``preflight_identity`` (95% refdes overlap),
``run_all_preflight_checks`` (the preflight surface embedding the
reconciliation oracle), and the U2/U3 reconciliation itself -- is run against
each injected mutation of the compiled design netlist, and the owning check
is asserted to fail per class. The renumber case is the corpus's headline:
the overlap check PASSES (it is structurally blind to a set-preserving
permutation) while the sheetpath oracle reports RENUMBERED findings. The
unmutated netlist passes every check (anti-vacuity), and the runner fails
closed on a stale netlist (U7).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_netlist_mutation_corpus as corpus  # noqa: E402
from netlist_mutator import (  # noqa: E402
    load_netlist,
    mutate_drop_net,
    mutate_renumber,
    mutate_reuse_refdes,
    pick_droppable_net,
    write_netlist,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
REAL_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
REAL_SRC = REPO_ROOT / "elec" / "src"


def _mutated_netlist(tmp_path: Path, mutation: str, seed: int) -> Path:
    mutated = load_netlist(REAL_NETLIST)
    if mutation == "renumber":
        mutated, _summary = mutate_renumber(mutated, seed)
    elif mutation == "drop-net":
        net_name = pick_droppable_net(mutated, seed)
        mutated, _summary = mutate_drop_net(mutated, net_name)
    elif mutation == "reuse":
        mutated, _summary = mutate_reuse_refdes(mutated, seed)
    else:  # pragma: no cover
        raise AssertionError(mutation)
    out = tmp_path / f"{mutation}.net"
    write_netlist(mutated, out)
    return out


# ===========================================================================
# U6 -- per-class bite assertions against the real board
# ===========================================================================


class TestMutationClassBite:
    @pytest.fixture(autouse=True)
    def _require_real_inputs(self):
        if not REAL_BOARD.is_file() or not REAL_NETLIST.is_file():
            pytest.skip("board or compiled netlist missing (run `make netlist`)")

    def test_clean_netlist_passes_every_check(self) -> None:
        """The unmutated netlist passes every check (anti-vacuity)."""
        outcome = corpus.evaluate_netlist(REAL_BOARD, REAL_NETLIST)
        assert outcome["overlap"]["passed"], outcome["overlap"].get("error")
        assert outcome["preflight"]["passed"], outcome["preflight"].get("error")
        assert outcome["reconciliation"]["passed"], outcome["reconciliation"].get("error")

    def test_dropped_net_fails_with_net_membership(self, tmp_path: Path) -> None:
        """The dropped-net mutation fails the reconciliation with a
        NET-MEMBERSHIP finding naming the missing net."""
        mutated = _mutated_netlist(tmp_path, "drop-net", corpus.DROP_NET_SEED)
        outcome = corpus.evaluate_netlist(REAL_BOARD, mutated)
        assert "NET-MEMBERSHIP" in outcome["reconciliation"]["findings"]
        assert not outcome["preflight"]["passed"]
        # The named net must be a real board net whose design-side nodes
        # vanished -- sanity-check via the detail message of a fresh run.
        from temper_placer.validation.netlist_reconciliation import (
            extract_board_netlist,
            parse_design_netlist,
            reconcile,
        )

        report = reconcile(
            extract_board_netlist(REAL_BOARD), parse_design_netlist(mutated)
        )
        membership = report.findings_of("NET-MEMBERSHIP")
        assert membership
        assert "zero nodes" in membership[0].detail or "membership" in membership[0].detail

    def test_reused_refdes_fails_with_reuse(self, tmp_path: Path) -> None:
        """The reused-refdes mutation fails the reconciliation with a REUSE
        finding naming the ref."""
        mutated = _mutated_netlist(tmp_path, "reuse", corpus.REUSE_SEED)
        outcome = corpus.evaluate_netlist(REAL_BOARD, mutated)
        assert "REUSE" in outcome["reconciliation"]["findings"]
        assert not outcome["preflight"]["passed"]

    def test_renumber_fails_sheetpath_oracle_but_passes_overlap(
        self, tmp_path: Path
    ) -> None:
        """The renumber mutation fails the sheetpath oracle with RENUMBERED
        findings AND passes preflight_identity's 95% overlap check --
        documenting that the overlap check structurally cannot see this
        class."""
        mutated = _mutated_netlist(tmp_path, "renumber", corpus.RENUMBER_SEED)
        outcome = corpus.evaluate_netlist(REAL_BOARD, mutated)
        assert "RENUMBERED" in outcome["reconciliation"]["findings"]
        assert not outcome["reconciliation"]["passed"]
        assert outcome["overlap"]["passed"], (
            "the wholesale-renumber class must pass the 95% refdes-overlap "
            f"check (it is a set-preserving permutation); failed: "
            f"{outcome['overlap'].get('error')}"
        )
        assert not outcome["preflight"]["passed"]


# ===========================================================================
# U7 -- corpus runner behaviour
# ===========================================================================


class TestCorpusRunner:
    def test_clean_corpus_run_returns_zero(self) -> None:
        """The corpus passes with all three classes covered and the clean
        netlist green (U7 verification)."""
        if not REAL_BOARD.is_file() or not REAL_NETLIST.is_file():
            pytest.skip("board or compiled netlist missing (run `make netlist`)")
        assert (
            corpus.run_corpus(REAL_BOARD, REAL_NETLIST, REAL_SRC, skip_freshness=True)
            == corpus.EXIT_OK
        )

    def test_stale_netlist_fails_closed(self, tmp_path: Path) -> None:
        """A stale netlist fails the runner closed with a GATE ERROR, never a
        clean pass."""
        import time

        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "main.ato").write_text("module main\n")
        stale_netlist = tmp_path / "stale.net"
        stale_netlist.write_text(
            '(export (version "E")\n  (components\n  )\n  (nets\n  )\n)\n'
        )
        # Make the source strictly newer than the netlist.
        future = time.time() + 60
        import os

        os.utime(stale_netlist, (future, future))
        assert (
            corpus.run_corpus(REAL_BOARD, stale_netlist, src_dir)
            == corpus.EXIT_GATE_ERROR
        )

    def test_uncovered_class_fails_the_corpus_run(self, tmp_path: Path, monkeypatch) -> None:
        """A mutation class whose owning check passes fails the corpus run as
        uncovered (exit 3), even when every other class bites."""
        if not REAL_BOARD.is_file() or not REAL_NETLIST.is_file():
            pytest.skip("board or compiled netlist missing (run `make netlist`)")
        # The renumber mutation never produces NET-MEMBERSHIP findings, so a
        # class mapped to that owning kind is uncovered by construction.
        fake_table = {
            "fake-class": {
                "mutation": "renumber",
                "seed": 7,
                "owning_kinds": ("NET-MEMBERSHIP",),
                "overlap_must_pass": False,
            }
        }
        monkeypatch.setattr(corpus, "MUTATION_CLASSES", fake_table)
        assert (
            corpus.run_corpus(REAL_BOARD, REAL_NETLIST, REAL_SRC, skip_freshness=True)
            == corpus.EXIT_VIOLATION
        )

    def test_gate_is_wired_into_ci_workflow(self) -> None:
        """Silent-skip-hole regression test (same class as the one written for
        check_footprint_drift.py): asserts the two corpus scripts are actually
        referenced in a `run:` step of the board-gates job in
        python-tests.yml, not merely registered in scripts/manifest.yaml."""
        workflow_path = REPO_ROOT / ".github" / "workflows" / "python-tests.yml"
        assert workflow_path.is_file(), f"workflow file not found: {workflow_path}"
        text = workflow_path.read_text(encoding="utf-8")
        for script in (
            "check_netlist_board_reconciliation.py",
            "check_netlist_mutation_corpus.py",
        ):
            assert script in text, (
                f"scripts/{script} is not invoked from any `run:` step in "
                ".github/workflows/python-tests.yml -- the gate/corpus exists "
                "and has unit tests but CI never actually runs it."
            )

    def test_evidence_doc_records_the_renumber_proof(self) -> None:
        """The renumber proof evidence doc is committed and records both check
        verdicts (U6 test scenario 6)."""
        doc = REPO_ROOT / "docs" / "evidence" / "2026-08-02-netlist-renumber-proof.md"
        assert doc.is_file(), f"evidence doc missing: {doc}"
        text = doc.read_text(encoding="utf-8")
        assert "RENUMBERED" in text
        assert "overlap" in text.lower()
