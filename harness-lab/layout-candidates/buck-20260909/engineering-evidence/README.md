# Historical engineering run excerpts

These are unmodified report excerpts from the local run
`harness-lab/runs/engineering-audit2-compact-v4/`. Its recorded absolute
`evidence_directory` identifies the original host location. The full run is
retained locally and gitignored; these excerpts are **not a portable trusted
qualification receipt**. The report is blocked and grants no admission.

The candidate bytes, native DRC and layout measurements are retained in the
parent directory. The source inventory and toolchain here document what was
used. A clean checkout can collect fresh complete evidence with:

```sh
python3 harness-lab/engineering_host.py /tmp/buck-engineering-fresh \
  --board harness-lab/layout-candidates/buck-20260909/candidate.kicad_pcb
```

Use a fresh output directory and the documented Atopile/KiCad toolchain.
Regeneration creates new provenance; it must not be represented as the
original run or as a qualified reference.
