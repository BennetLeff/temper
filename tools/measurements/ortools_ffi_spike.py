#!/usr/bin/env python3
"""Evidence for the OR-Tools FFI spike: can Rust drive CP-SAT without Python?

Run:  uv run --no-sync python tools/measurements/ortools_ffi_spike.py

Prints the four findings recorded in
docs/evidence/2026-08-06-ortools-ffi-spike.md, and writes a
FileDescriptorSet to /tmp/cp_model_fds.bin -- prost-build's input format,
which is what makes the Rust structs obtainable with no OR-Tools source
checkout.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def lib_symbols() -> None:
    """1. Does the shipped dylib export the C++ solve entry points?"""
    import ortools

    libs = pathlib.Path(ortools.__file__).parent / ".libs"
    cand = sorted(libs.glob("libortools*.dylib")) + sorted(libs.glob("libortools*.so"))
    if not cand:
        print("  [1] libortools: NOT FOUND")
        return
    lib = cand[0]
    print(f"  [1] {lib.name} ({lib.stat().st_size // 1024 // 1024} MB)")
    try:
        nm = subprocess.run(["nm", "-gU", str(lib)], capture_output=True, text=True, timeout=120)
        dem = subprocess.run(["c++filt"], input=nm.stdout, capture_output=True, text=True, timeout=120)
        for line in dem.stdout.splitlines():
            if "sat::Solve(" in line or "sat::SolveWithParameters(" in line:
                print(f"      exports: {line.split(' T ')[-1][:96]}")
    except Exception as exc:  # nm/c++filt are not on every platform
        print(f"      (symbol dump unavailable: {exc})")


def schema_is_recoverable() -> None:
    """2/3. Is the proto schema obtainable without an OR-Tools source build?"""
    from google.protobuf import descriptor_pb2

    from ortools.sat import cp_model_pb2 as pb

    seen: set[str] = set()
    fds = descriptor_pb2.FileDescriptorSet()

    def add(fd) -> None:
        if fd.name in seen:
            return
        seen.add(fd.name)
        for dep in fd.dependencies:
            add(dep)
        proto = descriptor_pb2.FileDescriptorProto()
        fd.CopyToProto(proto)
        fds.file.append(proto)

    add(pb.DESCRIPTOR)
    out = pathlib.Path("/tmp/cp_model_fds.bin")
    out.write_bytes(fds.SerializeToString())
    print(f"  [2] FileDescriptorSet: {out} ({out.stat().st_size} bytes, "
          f"{len(fds.file)} file(s), {len(pb.DESCRIPTOR.message_types_by_name)} messages)")
    print("      prost_build::Config::compile_fds() consumes this directly.")


def risky_apis_are_proto_fields() -> int:
    """4. The APIs that would sink this if they were Python-side logic."""
    from ortools.sat import cp_model_pb2 as pb

    resp = {f.name for f in pb.DESCRIPTOR.message_types_by_name["CpSolverResponse"].fields}
    model = {f.name for f in pb.DESCRIPTOR.message_types_by_name["CpModelProto"].fields}
    checks = [
        ("CpSolverResponse", "sufficient_assumptions_for_infeasibility", resp),
        ("CpSolverResponse", "status", resp),
        ("CpSolverResponse", "solution", resp),
        ("CpSolverResponse", "objective_value", resp),
        ("CpSolverResponse", "wall_time", resp),
        ("CpModelProto", "assumptions", model),
        ("CpModelProto", "solution_hint", model),
    ]
    missing = 0
    for msg, field, have in checks:
        ok = field in have
        missing += not ok
        print(f"  [4] {'OK     ' if ok else 'MISSING'} {msg}.{field}")
    return missing


def main() -> int:
    lib_symbols()
    schema_is_recoverable()
    missing = risky_apis_are_proto_fields()
    if missing:
        print(f"\n  {missing} expected proto field(s) missing -- re-read the spike doc "
              "before trusting its verdict.", file=sys.stderr)
        return 1
    print("\n  Verdict: the CP-SAT interface is bytes-in / bytes-out. A Rust "
          "implementation needs prost structs plus a thin C++ shim, and no "
          "Python modelling logic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
