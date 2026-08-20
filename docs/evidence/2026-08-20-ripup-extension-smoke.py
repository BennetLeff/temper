# provenance: commit=bc3a19b063a26eb0eabc880494d1133496f0cdfb dirty=false
# Branch agent/ripup-production-path, branched from bc3a19b06
# (origin/agent/per-pairing-placement-route). The A* core these scripts
# instrument is byte-identical to origin/main at that commit. See
# docs/evidence/2026-08-20-ripup-production-path.md.
# pcb/temper.kicad_pcb sha256
# 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified
# unchanged before AND after; never opened for writing. Every board written by
# these scripts goes to a scratch path outside the repo.
import importlib
import sys

MODS = [
    "temper_constraint_compiler",
    "temper_constraints",
    "temper_design_bundle_python",
    "temper_drc_rs",
    "temper_geometry",
    "temper_io_types",
    "temper_orchestration",
    "temper_quality_oracle",
    "temper_rust_router",
    "temper_thermal",
]
bad = []
for m in MODS:
    try:
        importlib.import_module(m)
        print(f"  OK   {m}")
    except Exception as e:  # noqa: BLE001
        bad.append((m, repr(e)))
        print(f"  FAIL {m}: {e!r}")
print(f"import-smoke: {len(MODS) - len(bad)}/{len(MODS)} loadable")
sys.exit(1 if bad else 0)
