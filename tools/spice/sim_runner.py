"""
ngspice simulation runner.

Wraps ngspice invocation, performs parameter substitution, parses output
into structured CornerResult objects, and handles convergence failures
gracefully.

Usage:
    python -m tools.spice.sim_runner testbench.cir
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.spice.corner_results import CornerResult

NGSPICE_BIN = shutil.which("ngspice") or "ngspice"


def run_simulation(
    cir_file: str | Path,
    params: dict[str, float] | None = None,
    temp_c: float | None = None,
    timeout_s: int = 120,
) -> CornerResult:
    """Run an ngspice simulation and return structured results.

    Args:
        cir_file: Path to a self-contained .cir netlist file.
        params: Parameter overrides (e.g. VDC, F_SW, R_PAN, DUTY).
        temp_c: Simulation temperature in Celsius (sets .temp directive).
        timeout_s: Maximum seconds to wait for ngspice.

    Returns:
        CornerResult with parsed metrics. convergence_error=True on failure.
    """
    try:
        cir_path = Path(cir_file)
        original = cir_path.read_text()
    except FileNotFoundError:
        return CornerResult(
            corner_name=_corner_name(params),
            Vbus=params.get("VDC", 320.0) if params else 320.0,
            Iload=params.get("ILOAD", 0.0) if params else 0.0,
            Tj=temp_c or 25.0,
            Zload_angle=params.get("ZLOAD_ANGLE", 0.0) if params else 0.0,
            convergence_error=True,
            error_message=f"File not found: {cir_file}",
        )

    modified = _apply_params(original, params, temp_c)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".cir", delete=False
    ) as tf:
        tf.write(modified)
        temp_path = tf.name

    try:
        completed = subprocess.run(
            [NGSPICE_BIN, "-b", temp_path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return _parse_output(
            completed.stdout,
            completed.stderr,
            params,
            temp_c,
        )
    except subprocess.TimeoutExpired:
        return CornerResult(
            corner_name=_corner_name(params),
            Vbus=params.get("VDC", 320.0) if params else 320.0,
            Iload=params.get("ILOAD", 0.0) if params else 0.0,
            Tj=temp_c or 25.0,
            Zload_angle=params.get("ZLOAD_ANGLE", 0.0) if params else 0.0,
            convergence_error=True,
            error_message="ngspice timeout",
        )
    except FileNotFoundError:
        return CornerResult(
            corner_name=_corner_name(params),
            Vbus=params.get("VDC", 320.0) if params else 320.0,
            Iload=params.get("ILOAD", 0.0) if params else 0.0,
            Tj=temp_c or 25.0,
            Zload_angle=params.get("ZLOAD_ANGLE", 0.0) if params else 0.0,
            convergence_error=True,
            error_message="ngspice binary not found",
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _apply_params(
    netlist: str,
    params: dict[str, float] | None,
    temp_c: float | None,
) -> str:
    """Substitute parameters into the netlist.

    Adds or replaces .param lines. If a param exists, the value is updated;
    otherwise a new .param line is added.
    """
    if not params and temp_c is None:
        return netlist

    lines = netlist.split("\n")
    result: list[str] = []

    existing_params: dict[str, int] = {}
    for i, line in enumerate(lines):
        m = re.match(r"\.param\s+(\w+)\s*=\s*[\d.]+", line)
        if m:
            existing_params[m.group(1)] = i

    injected_temp = False
    injected_params = set()

    for _i, line in enumerate(lines):
        if temp_c is not None and not injected_temp:
            if line.strip().startswith(".options"):
                result.append(line)
                result.append(f".temp {temp_c}")
                injected_temp = True
                continue

        if params:
            m = re.match(r"\.param\s+(\w+)\s*=", line)
            if m:
                pname = m.group(1)
                if pname in params:
                    result.append(f".param {pname}={params[pname]}")
                    injected_params.add(pname)
                    continue

        result.append(line)

    if params:
        for pname, pval in params.items():
            if pname not in injected_params:
                result.append(f".param {pname}={pval}")

    if temp_c is not None and not injected_temp:
        result.insert(0, f".temp {temp_c}")

    return "\n".join(result)


_METRIC_RE = re.compile(
    r"(\w[\w_]*)\s*=\s*([\d.\-+eE]+)(?:\s|$)"
)
_MEAS_RE = re.compile(
    r"Measurement:\s+(\w[\w_]*)\s*"
)


def _parse_output(
    stdout: str,
    stderr: str,
    params: dict[str, float] | None,
    temp_c: float | None,
) -> CornerResult:
    """Parse ngspice output into a CornerResult."""
    corner_name = _corner_name(params)
    vbus = params.get("VDC", 320.0) if params else 320.0
    iload = params.get("ILOAD", 0.0) if params else 0.0
    tj = temp_c or params.get("TJ", 25.0) if params else 25.0
    zload = params.get("ZLOAD_ANGLE", 0.0) if params else 0.0

    convergence_error = "tran simulation(s) aborted" in stderr.lower() or \
        "convergence" in stderr.lower() or \
        "doAnalyses: iteration limit reached" in stderr.lower() or \
        "singular matrix" in stderr.lower()

    if convergence_error:
        return CornerResult(
            corner_name=corner_name,
            Vbus=vbus,
            Iload=iload,
            Tj=tj,
            Zload_angle=zload,
            convergence_error=True,
            error_message=stderr.strip()[:500],
        )

    metrics: dict[str, float] = {}

    all_lines = stdout.split("\n")
    for _i, line in enumerate(all_lines):
        val_match = re.search(r"(\w[\w_]*)\s*=\s*([\d.\-+eE]+)", line)
        if val_match:
            name = val_match.group(1)
            try:
                metrics[name] = float(val_match.group(2))
            except ValueError:
                pass

    if not metrics:
        for _i_fallback, line in enumerate(all_lines):
            m = _MEAS_RE.search(line)
            if m:
                meas_name = m.group(1)
                for j in range(_i_fallback + 1, min(_i_fallback + 3, len(all_lines))):
                    needle = f"{meas_name} = "
                    if needle in all_lines[j]:
                        val_match = re.search(r"=\s*([\d.\-+eE]+)", all_lines[j])
                        if val_match:
                            try:
                                metrics[meas_name] = float(val_match.group(1))
                            except ValueError:
                                pass
                        break

    vge_peak = (
        metrics.get("V_ge_hs_max")
        or metrics.get("v_ge_hs_max")
        or metrics.get("V_ge_hs_max")
    )
    vge_overshoot = None
    if vge_peak is not None:
        vge_dc = params.get("VGE_ON", 15.0) if params else 15.0
        vge_overshoot = ((vge_peak - vge_dc) / vge_dc) * 100.0

    vce_peak = (
        metrics.get("V_ce_hs_max")
        or metrics.get("v_ce_hs_max")
        or metrics.get("V_mid_max")
        or metrics.get("v_mid_max")
    )
    tank_rms = (
        metrics.get("I_tank_rms")
        or metrics.get("i_tank_rms")
    )
    switching_loss = (
        metrics.get("E_sw_total_mJ")
        or metrics.get("e_sw_total_mj")
    )

    tj_primary = (
        metrics.get("Tj_primary")
        or metrics.get("tj_primary")
    )

    return CornerResult(
        corner_name=corner_name,
        Vbus=vbus,
        Iload=iload,
        Tj=tj,
        Zload_angle=zload,
        Vge_peak=vge_peak,
        Vge_overshoot_pct=vge_overshoot,
        Vce_peak=vce_peak,
        tank_current_rms=tank_rms,
        switching_loss_mJ=switching_loss,
        Tj_primary=tj_primary,
        convergence_error=False,
        extra_metrics=metrics,
    )


def _corner_name(params: dict[str, float] | None) -> str:
    """Generate a human-readable corner name."""
    if not params:
        return "nominal"
    vbus = params.get("VDC", 320)
    iload = params.get("ILOAD", 0)
    tj = params.get("TJ", 25)
    zload = params.get("ZLOAD_ANGLE", 0)
    return f"V{vbus:.0f}_I{iload:.0f}_T{tj:.0f}_Z{zload:.0f}"


def check_ngspice_available() -> bool:
    """Check if ngspice is installed and callable."""
    return shutil.which("ngspice") is not None


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run ngspice simulation")
    parser.add_argument("cir_file", help="Path to .cir netlist file")
    parser.add_argument("--vbus", type=float, help="DC bus voltage override")
    parser.add_argument("--iload", type=float, help="Load current override")
    parser.add_argument("--temp", type=float, help="Temperature in Celsius")
    parser.add_argument("--zload", type=float, help="Load impedance angle")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    params: dict[str, float] = {}
    if args.vbus is not None:
        params["VDC"] = args.vbus
    if args.iload is not None:
        params["ILOAD"] = args.iload
    if args.temp is not None:
        params["TJ"] = args.temp
    if args.zload is not None:
        params["ZLOAD_ANGLE"] = args.zload

    result = run_simulation(args.cir_file, params=params, temp_c=args.temp)

    if args.json:
        import json
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"Corner: {result.corner_name}")
        print(f"  Convergence: {'FAIL' if result.convergence_error else 'OK'}")
        if not result.convergence_error:
            print(f"  Vge_peak: {result.Vge_peak}")
            print(f"  Vge_overshoot: {result.Vge_overshoot_pct}%")
            print(f"  Vce_peak: {result.Vce_peak}")
            print(f"  I_tank_rms: {result.tank_current_rms}")
            print(f"  Tj_primary: {result.Tj_primary}")
        if result.error_message:
            print(f"  Error: {result.error_message[:200]}")


if __name__ == "__main__":
    main()
