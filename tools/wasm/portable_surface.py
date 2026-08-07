#!/usr/bin/env python3
"""Measure the Rust test surface that survives `--no-default-features`.

Unit U2 of the WASM Verification Tier Phase 0 plan.  For each Phase 0 crate
(`temper-drc-rs`, `temper-geometry`) this runs:

    cargo test --no-run --message-format=json            # default features
    cargo test --no-run --no-default-features --message-format=json

then executes every compiled test binary with `--list`, collects the test
function names, and emits a JSON delta: the tests present in the default
build but absent from the `--no-default-features` build.  That delta is the
test surface the wasm tier cannot run.

pyo3 note: test binaries built with the `python` feature use the
`extension-module` ABI and do not link libpython, so on macOS their flat
namespace lookup for CPython symbols fails at load.  `--list` is retried
with the interpreter's libpython preloaded (DYLD_INSERT_LIBRARIES on macOS,
LD_PRELOAD on Linux) when the plain invocation fails.

tools/ is deliberately outside scripts/manifest.yaml scope.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CRATES = ("temper-drc-rs", "temper-geometry")
PRELOAD_ENV = "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"
LIST_TIMEOUT_S = 300
CARGO_TIMEOUT_S = 1800


def _libpython_shared() -> str | None:
    """Path to the running interpreter's shared libpython, or None.

    `pyo3` test binaries built with the `extension-module` feature reference
    CPython symbols but do not link libpython.  `sysconfig.LDLIBRARY` can be
    the static archive on some distributions, so probe for the shared object
    of the same stem next to it.
    """
    try:
        import sysconfig

        libdir = sysconfig.get_config_var("LIBDIR")
        libname = sysconfig.get_config_var("LDLIBRARY") or ""
    except ImportError:
        return None
    if not libdir:
        return None
    libdir = Path(libdir)
    if libname.endswith((".dylib", ".so")):
        candidate = libdir / libname
        if candidate.exists():
            return str(candidate)
    stem = libname.rsplit(".", 1)[0] if "." in libname else libname
    if not stem:
        return None
    for extension in (".dylib", ".so"):
        candidate = libdir / f"{stem}{extension}"
        if candidate.exists():
            return str(candidate)
    return None


def _parse_list(stdout: str) -> list[str]:
    """Test names from `test_binary --list` output."""
    return [line.rsplit(": ", 1)[0] for line in stdout.splitlines() if line.endswith(": test")]


def _list_tests(executable: Path) -> tuple[list[str], bool]:
    """Run `--list` on one test binary, retrying with libpython preloaded.

    Returns (test_names, preload_needed).  A binary that needs the preload
    only needs it because it carries pyo3's `extension-module` surface.
    """
    plain = subprocess.run(
        [str(executable), "--list"],
        capture_output=True,
        text=True,
        timeout=LIST_TIMEOUT_S,
    )
    if plain.returncode == 0:
        return _parse_list(plain.stdout), False
    libpython = _libpython_shared()
    if not libpython:
        raise RuntimeError(
            f"{executable.name}: --list failed ({plain.returncode}) and no libpython found"
        )
    env = dict(os.environ)
    env[PRELOAD_ENV] = libpython
    retry = subprocess.run(
        [str(executable), "--list"],
        capture_output=True,
        text=True,
        timeout=LIST_TIMEOUT_S,
        env=env,
    )
    if retry.returncode != 0:
        detail = (retry.stderr or retry.stdout or "").strip().splitlines()
        raise RuntimeError(
            f"{executable.name}: --list failed with preload ({retry.returncode}): {detail[-1] if detail else 'no output'}"
        )
    return _parse_list(retry.stdout), True


def _cargo_test_no_run(crate_dir: Path, no_default_features: bool) -> tuple[int, dict[str, dict]]:
    """Run one `cargo test --no-run` configuration; return (exit, binaries).

    `binaries` maps target name -> {"executable": str, "tests": [...],
    "preload_needed": bool}.  Targets whose build failed are absent.
    """
    command = ["cargo", "test", "--no-run", "--message-format=json"]
    if no_default_features:
        command.append("--no-default-features")
    completed = subprocess.run(
        command,
        cwd=crate_dir,
        capture_output=True,
        text=True,
        timeout=CARGO_TIMEOUT_S,
    )
    binaries: dict[str, dict] = {}
    for line in completed.stdout.splitlines():
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("reason") != "compiler-artifact":
            continue
        profile = message.get("profile", {})
        target = message.get("target", {})
        if not profile.get("test") or not target.get("name"):
            continue
        filenames = message.get("filenames") or []
        if not filenames:
            continue
        executable = Path(filenames[0])
        if not executable.exists():
            continue
        tests, preload = _list_tests(executable)
        binaries[target["name"]] = {
            "executable": str(executable),
            "tests": sorted(tests),
            "preload_needed": preload,
        }
    return completed.returncode, binaries


def _crate_measurement(crate: str) -> dict:
    crate_dir = REPO_ROOT / "packages" / crate
    default_rc, default_binaries = _cargo_test_no_run(crate_dir, no_default_features=False)
    nodefault_rc, nodefault_binaries = _cargo_test_no_run(crate_dir, no_default_features=True)

    default_tests: dict[str, list[str]] = {k: v["tests"] for k, v in default_binaries.items()}
    nodefault_tests: dict[str, list[str]] = {k: v["tests"] for k, v in nodefault_binaries.items()}

    gated_out_tests: list[str] = []
    missing_targets: list[dict] = []
    for target in sorted(default_tests):
        if target not in nodefault_tests:
            missing_targets.append(
                {"target": target, "default_test_count": len(default_tests[target])}
            )
            gated_out_tests.extend(default_tests[target])
            continue
        gated_out_tests.extend(sorted(set(default_tests[target]) - set(nodefault_tests[target])))
    surplus = sorted(set(nodefault_tests) - set(default_tests))

    default_count = sum(len(t) for t in default_tests.values())
    nodefault_count = sum(len(t) for t in nodefault_tests.values())

    return {
        "default_features": {
            "build_ok": default_rc == 0,
            "cargo_exit_code": default_rc,
            "binaries": default_binaries,
            "total_test_count": default_count,
        },
        "no_default_features": {
            "build_ok": nodefault_rc == 0,
            "cargo_exit_code": nodefault_rc,
            "binaries": nodefault_binaries,
            "total_test_count": nodefault_count,
        },
        "delta": {
            "test_count_default": default_count,
            "test_count_no_default_features": nodefault_count,
            "gated_out_count": len(gated_out_tests),
            "gated_out_tests": sorted(gated_out_tests),
            "targets_missing_in_no_default_features": missing_targets,
            "surplus_targets_in_no_default_features": surplus,
        },
    }


def _revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _measure() -> dict:
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "revision": _revision(),
        "repo_root": str(REPO_ROOT),
        "crates": {crate: _crate_measurement(crate) for crate in CRATES},
    }


def _print_summary(measurement: dict) -> None:
    for crate, data in measurement["crates"].items():
        default = data["default_features"]
        nodefault = data["no_default_features"]
        delta = data["delta"]
        default_status = (
            "build ok" if default["build_ok"] else f"build exit {default['cargo_exit_code']}"
        )
        nodefault_status = (
            "build ok" if nodefault["build_ok"] else f"build exit {nodefault['cargo_exit_code']}"
        )
        print(f"=== {crate} @ {measurement['revision'][:10]} ===")
        print(f"  default features:      {default['total_test_count']} tests ({default_status})")
        print(
            f"  --no-default-features: {nodefault['total_test_count']} tests ({nodefault_status})"
        )
        print(f"  delta (gated out):     {delta['gated_out_count']} tests")
        if delta["targets_missing_in_no_default_features"]:
            for missing in delta["targets_missing_in_no_default_features"]:
                print(
                    f"  target missing under --no-default-features: "
                    f"{missing['target']} ({missing['default_test_count']} tests, build failure)"
                )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        help="write the JSON delta to this path (default: stdout)",
        type=Path,
        default=None,
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    measurement = _measure()
    _print_summary(measurement)
    payload = json.dumps(measurement, indent=2)
    if args.out:
        args.out.write_text(payload + "\n")
        print(f"\nwrote {args.out}")
    else:
        print("\n" + payload)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
