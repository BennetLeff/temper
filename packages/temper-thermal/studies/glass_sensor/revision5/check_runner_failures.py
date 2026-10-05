"""Verify that a failed Rust-test executable aborts both study runners."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    real_rustc = shutil.which("rustc")
    if real_rustc is None:
        raise RuntimeError("rustc unavailable")
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="temper-r5-runner-fault-") as temporary:
        temp = Path(temporary)
        project = temp / "revision5"
        for group in ["thermal", "safety"]:
            target = project / group
            target.mkdir(parents=True)
            for name in ["run.sh", "main.rs", "model.rs", "inputs.sha256"]:
                source = ROOT / group / name
                if source.exists():
                    shutil.copy2(source, target / name)
        (project / "mechanical").mkdir()
        shutil.copy2(
            ROOT / "mechanical/thermal_geometry.csv", project / "mechanical/thermal_geometry.csv"
        )
        # Works in the final study tree; the scratch fallback supports this integration check.
        kernel = ROOT.parent / "model.rs"
        if not kernel.exists():
            kernel = Path(
                "/Users/bennet/.codex/worktrees/glass-sensor-simulation/temper/packages/temper-thermal/studies/glass_sensor/model.rs"
            )
        shutil.copy2(kernel, temp / "model.rs")
        stub_dir = temp / "compiler-stub"
        stub_dir.mkdir()
        stub = stub_dir / "rustc"
        stub.write_text(
            "#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\n"
            "args=sys.argv[1:]\n"
            'if "--test" in args:\n'
            ' output=Path(args[args.index("-o")+1])\n'
            ' output.write_text("#!/bin/sh\\nexit 7\\n")\n'
            " output.chmod(0o755)\n"
            "else:\n"
            f" os.execv({real_rustc!r},[{real_rustc!r},*args])\n"
        )
        stub.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = str(stub_dir) + os.pathsep + environment["PATH"]
        for group in ["thermal", "safety"]:
            completed = subprocess.run(
                ["sh", str(project / group / "run.sh")],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            receipt_exists = (project / group / "results/run-inputs.sha256").exists()
            physics_outputs = list((project / group / "results").glob("*.csv"))
            if completed.returncode != 7 or receipt_exists or physics_outputs:
                raise RuntimeError(
                    f"{group}: failed-test propagation broke: {completed.returncode}\n{completed.stdout}\n{completed.stderr}"
                )
            outcomes.append(
                {
                    "runner": group,
                    "injected_test_exit": 7,
                    "observed_runner_exit": completed.returncode,
                    "physics_csvs_emitted": len(physics_outputs),
                    "receipt_emitted": receipt_exists,
                }
            )
    (ROOT / "runner-failure-check.json").write_text(
        json.dumps(
            {
                "checks": outcomes,
                "method": "Isolated copied runner with test compiler output replaced by an executable that exits 7; production source unchanged.",
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(outcomes, indent=2))


if __name__ == "__main__":
    main()
