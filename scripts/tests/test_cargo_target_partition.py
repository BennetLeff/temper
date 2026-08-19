"""The extension-module target-dir partition, and its three implementations.

The partition (see scripts/_lib/cargo_target.py) is implemented three times,
because each covers a path the others cannot reach:

  1. the ``cargo`` PATH wrapper -- direct cargo/maturin calls in any shell
  2. the Makefile -- ``make`` recipes and CI, where no wrapper is installed
  3. scripts/_lib/cargo_target.py -- the gates that must know where to look

Triplicated logic drifts. These tests pin the three together, and pin the
behaviour to the measured incident rather than to the current spelling: the
wrapper is *executed*, not merely grepped, so a bash edit that changes what it
does fails here even if the constants still match.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib.cargo_target import (  # noqa: E402
    EXTENSION_MODULE_FEATURE,
    EXTENSION_TARGET_SUFFIX,
    SHARED_TARGET_BASENAME,
    extension_target_dir,
    is_extension_module_build,
    shared_target_dir,
    target_dir_for,
    with_extension_suffix,
)
from install_cargo_target_dir_guard import wrapper_source  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestFeatureDetection:
    """`pyo3/extension-module` is the discriminator, in every spelling cargo takes.

    Captured live from maturin 1.9 on this repo's temper-geometry:

        cargo rustc --profile release --features python \
             --features pyo3/extension-module --message-format json-... \
             --manifest-path .../Cargo.toml --lib --crate-type cdylib

    but maturin's exact form is maturin's business, so all three cargo-legal
    spellings must work or the partition silently stops applying on a maturin
    upgrade -- failing OPEN, straight back into the shared uplift path.
    """

    @pytest.mark.parametrize(
        "argv",
        [
            ["rustc", "--features", "pyo3/extension-module"],
            ["rustc", "--features=pyo3/extension-module"],
            ["build", "--features", "python,pyo3/extension-module"],
            ["build", "--features=python,pyo3/extension-module"],
            ["build", "--features", "python", "--features", "pyo3/extension-module"],
        ],
    )
    def test_extension_builds_are_detected(self, argv: list[str]) -> None:
        assert is_extension_module_build(argv)

    @pytest.mark.parametrize(
        "argv",
        [
            ["build", "--release"],
            ["check"],
            ["clippy", "--all-targets"],
            ["test", "--features", "python"],
            ["build", "--features", "wasm-registry-all"],
        ],
    )
    def test_ordinary_builds_are_not_diverted(self, argv: list[str]) -> None:
        """`--features python` alone must NOT divert.

        `python` pulls in pyo3 but still links libpython; only
        `extension-module` produces the un-importable-by-cargo cdylib that
        makes the two artifacts incompatible. Diverting on `python` would
        split the cache for `cargo test --features python`, which is a normal
        Rust workflow here, and buy nothing.
        """
        assert not is_extension_module_build(argv)


class TestDerivation:
    def test_extension_dir_is_the_shared_dir_plus_suffix(self, tmp_path: Path) -> None:
        assert extension_target_dir(tmp_path) == tmp_path / (
            SHARED_TARGET_BASENAME + EXTENSION_TARGET_SUFFIX
        )

    def test_both_dirs_are_siblings_under_one_root(self, tmp_path: Path) -> None:
        """Both stay SHARED across worktrees -- the split is by feature set,
        not by worktree. A per-worktree split would re-create the private
        caches behind three disk-exhaustion incidents (51 GB, 36.6 GB, ~74 GB).
        """
        assert shared_target_dir(tmp_path).parent == extension_target_dir(tmp_path).parent

    def test_suffix_application_is_idempotent(self, tmp_path: Path) -> None:
        """The Makefile pre-suffixes AND the wrapper suffixes the same call.

        Both are correct in isolation and both fire on `make extensions`, so
        without idempotence they compose into `target-shared-pyext-pyext`.
        """
        once = with_extension_suffix(tmp_path / SHARED_TARGET_BASENAME)
        assert with_extension_suffix(once) == once

    def test_target_dir_for_routes_by_argv(self, tmp_path: Path) -> None:
        assert target_dir_for(["build"], tmp_path) == shared_target_dir(tmp_path)
        assert target_dir_for(
            ["rustc", "--features", EXTENSION_MODULE_FEATURE], tmp_path
        ) == extension_target_dir(tmp_path)


class TestWrapperMatchesPython:
    """Execute the generated wrapper and compare it to the Python derivation.

    Grepping the bash for the suffix string would pass on a wrapper whose
    `case` arms were inverted. Running it does not.
    """

    def _run_wrapper(
        self, tmp_path: Path, argv: list[str], target_dir_env: str | None
    ) -> str:
        """Return the CARGO_TARGET_DIR the wrapper hands to the real cargo."""
        stub = tmp_path / "real-cargo"
        stub.write_text('#!/usr/bin/env bash\nprintf "%s" "${CARGO_TARGET_DIR:-<unset>}"\n')
        stub.chmod(0o755)

        wrapper = tmp_path / "cargo"
        wrapper.write_text(wrapper_source(stub, tmp_path / "canonical-root"))
        wrapper.chmod(0o755)

        env = dict(os.environ)
        env.pop("CARGO_TARGET_DIR", None)
        if target_dir_env is not None:
            env["CARGO_TARGET_DIR"] = target_dir_env
        result = subprocess.run(
            [str(wrapper), *argv], capture_output=True, text=True, env=env, cwd=str(tmp_path)
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def test_extension_build_is_diverted_from_an_explicit_target_dir(
        self, tmp_path: Path
    ) -> None:
        """The case that matters most: an explicitly-set CARGO_TARGET_DIR.

        Everything arriving via `make`, or via a shell that sourced
        cargo_shared_env.sh, has it set. If the wrapper deferred to it, the
        extension build would land straight back in the colliding directory --
        i.e. the partition would be a no-op for the most common path.
        """
        base = "/tmp/some-base"
        got = self._run_wrapper(
            tmp_path, ["rustc", "--features", EXTENSION_MODULE_FEATURE], base
        )
        assert got == base + EXTENSION_TARGET_SUFFIX
        assert got == str(with_extension_suffix(Path(base)))

    def test_ordinary_build_keeps_an_explicit_target_dir(self, tmp_path: Path) -> None:
        base = "/tmp/some-base"
        assert self._run_wrapper(tmp_path, ["build", "--release"], base) == base

    def test_already_suffixed_target_dir_is_not_double_suffixed(self, tmp_path: Path) -> None:
        base = "/tmp/some-base" + EXTENSION_TARGET_SUFFIX
        got = self._run_wrapper(
            tmp_path, ["rustc", "--features", EXTENSION_MODULE_FEATURE], base
        )
        assert got == base, f"double-suffixed to {got!r}"

    @pytest.mark.parametrize(
        "argv",
        [
            ["build", "--release"],
            ["check"],
            ["clippy", "--all-targets"],
            ["rustc", "--features", "pyo3/extension-module"],
            ["build", "--features=python,pyo3/extension-module"],
        ],
    )
    def test_wrapper_and_python_agree(self, tmp_path: Path, argv: list[str]) -> None:
        """Behavioural equivalence across the whole argv matrix."""
        base = "/tmp/agree-base"
        from_bash = self._run_wrapper(tmp_path, argv, base)
        from_python = (
            str(with_extension_suffix(Path(base)))
            if is_extension_module_build(argv)
            else base
        )
        assert from_bash == from_python


class TestMakefileAgrees:
    """The Makefile is the only one of the three that CI actually runs."""

    def test_makefile_derives_the_same_suffix(self) -> None:
        text = (REPO_ROOT / "Makefile").read_text()
        match = re.search(r"^CARGO_TARGET_DIR_PYEXT\s*:=\s*(.+)$", text, re.MULTILINE)
        assert match, "Makefile must define CARGO_TARGET_DIR_PYEXT"
        assert match.group(1).strip() == f"$(CARGO_TARGET_DIR){EXTENSION_TARGET_SUFFIX}", (
            f"Makefile suffix disagrees with EXTENSION_TARGET_SUFFIX "
            f"({EXTENSION_TARGET_SUFFIX!r}): {match.group(1)!r}"
        )

    def test_makefile_base_matches_shared_basename(self) -> None:
        text = (REPO_ROOT / "Makefile").read_text()
        match = re.search(r"^CARGO_TARGET_DIR\s*:=\s*(.+)$", text, re.MULTILINE)
        assert match and match.group(1).strip().endswith(f"/{SHARED_TARGET_BASENAME}")

    def test_extensions_target_builds_into_the_partitioned_dir(self) -> None:
        """`make extensions` must not hand maturin the colliding directory.

        This is the regression guard for the whole change: if a future edit
        drops the per-recipe override, `make extensions` silently resumes
        building into `target-shared` and the partition stops protecting the
        one command that exists to install these artifacts.
        """
        text = (REPO_ROOT / "Makefile").read_text()
        recipe = text.split("\nextensions:", 1)[1].split("\nextensions-check:", 1)[0]
        maturin_lines = [ln for ln in recipe.splitlines() if "maturin develop" in ln]
        assert maturin_lines, "expected `maturin develop` invocations in the extensions recipe"
        for line in maturin_lines:
            assert 'CARGO_TARGET_DIR="$(CARGO_TARGET_DIR_PYEXT)"' in line, (
                f"maturin invocation does not target the partitioned dir: {line.strip()!r}"
            )

    def test_extensions_target_verifies_before_declaring_done(self) -> None:
        """A build command that exits 0 over a broken artifact is the incident.

        Pins the three guards around the build loop: evict a poisoned cache
        first, stamp after, then FAIL on stale/unloadable/unstamped rather
        than printing "Done."
        """
        text = (REPO_ROOT / "Makefile").read_text()
        recipe = text.split("\nextensions:", 1)[1].split("\nextensions-check:", 1)[0]
        assert "check_cargo_uplift_poisoning.py" in recipe
        assert "write_extension_stamps.py" in recipe
        assert "--require-stamps" in recipe
