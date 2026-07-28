"""
Tests pinning the retired `--placer` CLI contract on `optimize`.

CP-SAT is the unconditional placer.  `--placer` and the JAX stack it used
to select are both gone (plan 2026-07-03-002; flag removed in 38092d65),
so every assertion here is a negative-existence or hard-rejection check.

Verifies that:
1. `--placer` is absent from `optimize --help`, as is any 'jax' choice
2. Passing `--placer` is a usage error, never a silently ignored flag
3. CP-SAT tuning flags (--cp-sat-timeout, etc.) are NOT exposed
   (see test_cp_sat_tuning_flags_not_currently_exposed)
4. `optimize` runs CP-SAT with no placer flag at all
"""

import pytest
from click.testing import CliRunner

from temper_placer.cli import main


class TestCpSatFlag:
    """Unit tests for the --placer CLI flag and CP-SAT options."""

    @pytest.fixture
    def runner(self) -> CliRunner:
        """Create a CLI runner."""
        return CliRunner()

    def test_placer_option_not_exposed(self, runner: CliRunner) -> None:
        """`--placer` is gone from `optimize`, and so is every 'jax' choice.

        VERIFIED 2026-07-28: `--placer` existed only to select between the
        JAX optimizer and CP-SAT.  The JAX stack was removed in plan
        2026-07-03-002 and the flag itself in 38092d65 ("remove deprecated
        real_board_inventory and jax-deprecated CLI option"), leaving CP-SAT
        as the unconditional placer.  This test previously asserted the flag
        AND a 'jax' choice were present, so it had been failing since that
        commit against a contract the project deliberately retired.

        Kept as a negative existence check rather than deleted: it is the
        only thing that would catch `--placer` -- or a JAX choice -- being
        reintroduced by a bad merge.  If either is restored intentionally,
        replace this with a positive check; do not delete it silently.
        """
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0, f"Help failed:\n{result.output}"
        assert "--placer" not in result.output, (
            "--placer reappeared in `optimize --help`. CP-SAT is the "
            "unconditional placer; if the option was restored on purpose, "
            "replace this test with a positive existence check."
        )
        # Scoped to placer *choices*, not any mention of JAX: `--profile-dir`
        # is still advertised as "Save JAX profiler trace to this directory"
        # and is accepted-but-never-read in the command body (a dead flag
        # tracked separately).  Asserting on the whole help text would make
        # this test fail for that unrelated reason.
        for choice in ("jax-deprecated", "--placer jax", "[jax|"):
            assert choice not in result.output, (
                f"A JAX placer choice ({choice!r}) reappeared in "
                f"`optimize --help`. The JAX optimizer stack was retired in "
                f"plan 2026-07-03-002.\n{result.output}"
            )

    def test_placer_flag_is_rejected_as_unknown_option(self, runner: CliRunner) -> None:
        """Passing `--placer` at all is a usage error, not a silent no-op.

        The dangerous failure mode is Click accepting and ignoring the flag:
        a caller asking for a specific placer would get CP-SAT regardless
        and never learn the request was dropped.
        """
        result = runner.invoke(main, ["optimize", "--placer", "cp-sat", "input.kicad_pcb"])
        assert result.exit_code == 2, (
            f"Expected a Click usage error (exit 2) for the removed --placer "
            f"option, got exit {result.exit_code}:\n{result.output}"
        )
        assert "No such option: --placer" in result.output, (
            f"Expected an unknown-option error naming --placer:\n{result.output}"
        )

    def test_cp_sat_tuning_flags_not_currently_exposed(self, runner: CliRunner) -> None:
        """--cp-sat-timeout/-workers/-grid-scale do not exist on `optimize`.

        VERIFIED 2026-07-18: these three flags were added in 2f3d4601
        ("add CP-SAT feasibility-first placer (U0-U8)") but are absent
        from the current `optimize` command entirely -- confirmed via
        `grep` across cli/__init__.py. `solve_placement()`'s underlying
        signature (placer/cp_sat/encoder.py) still accepts a `timeout_ms`
        parameter, but the CLI's call site
        (`solve_placement(netlist=..., board=..., ...)`) never passes it,
        silently relying on the function's own 1000ms default -- there is
        currently no way for a CLI user to control CP-SAT solve time.
        `--cp-sat-workers` and `--cp-sat-grid-scale` have no underlying
        parameter at all anymore; `solve_placement()`'s signature has no
        `workers` or `grid_scale` argument to wire to. This test
        previously asserted all three flags were present and had been
        silently broken (never actually run in CI) since whichever
        refactor removed them -- see docs/solutions/logic-errors/
        cli-cp-sat-tuning-flags-removed-stale-test.md.
        """
        result = runner.invoke(main, ["optimize", "--help"])
        assert result.exit_code == 0
        for flag in ("--cp-sat-timeout", "--cp-sat-workers", "--cp-sat-grid-scale"):
            assert flag not in result.output, (
                f"{flag} reappeared in `optimize --help` -- if this was "
                "intentionally restored, replace this test with a "
                "positive existence check instead of deleting it silently."
            )

    def test_jax_deprecated_is_rejected(self, runner: CliRunner) -> None:
        """`--placer jax-deprecated` no longer selects anything.

        Renamed from ``test_jax_deprecated_rejected``, which despite its
        name asserted the flag was *accepted*.  The JAX stack is gone; a
        caller naming it must get a hard error rather than a silent CP-SAT
        run under a JAX-shaped request.
        """
        result = runner.invoke(
            main,
            [
                "optimize",
                "--placer",
                "jax-deprecated",
                "nonexistent.kicad_pcb",
            ],
        )
        assert result.exit_code == 2, (
            f"Expected a usage error for the removed --placer option, "
            f"got exit {result.exit_code}:\n{result.output}"
        )
        assert "No such option: --placer" in result.output, (
            f"Expected an unknown-option error naming --placer:\n{result.output}"
        )

    def test_cp_sat_default_placer(self, runner: CliRunner) -> None:
        """Verify CP-SAT runs by default (no --placer flag needed)."""
        result = runner.invoke(
            main,
            [
                "optimize",
                "nonexistent.kicad_pcb",
            ],
        )
        # Should fail on input file existence, not on missing --placer flag
        assert result.exit_code != 0
        assert "nonexistent" in result.output

    def test_placer_rejects_invalid_value(self, runner: CliRunner) -> None:
        """An unrecognised `--placer` value fails on the option, not the value.

        Previously asserted Click's Choice-validation message.  With the
        option itself removed the rejection now happens one step earlier --
        still a hard failure, which is what matters, but for a different
        reason.  Asserting the reason keeps the test honest about which
        guard is doing the work.
        """
        result = runner.invoke(
            main,
            [
                "optimize",
                "--placer",
                "invalid_placer",
                "input.kicad_pcb",
            ],
        )
        assert result.exit_code == 2
        assert "No such option: --placer" in result.output, (
            f"Expected rejection at the option, not the value:\n{result.output}"
        )

    # test_cp_sat_timeout_default_value and test_cp_sat_workers_default_value
    # removed 2026-07-18: both asserted default values for flags that no
    # longer exist on `optimize` (see
    # test_cp_sat_tuning_flags_not_currently_exposed above, which already
    # covers their absence across all three flags in one place).
