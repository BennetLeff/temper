# Candidate-v5 validation commands

All commands were run from:

`/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`

The scratch board was:

`/tmp/temper-buck-followup-20260910/layout/candidate-v5/candidate.kicad_pcb`

The scratch KiCad library context was the sibling `fp-lib-table` and `fixture.pretty/` directory under the same candidate-v5 directory. The initial historical runs below had no `KICAD_CONFIG_HOME` override; the corrected final receipt at the end uses the repository's seeded temporary configuration.

## Native collector

The collector was run with this environment and argv:

```sh
PYTHONPATH=/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan/harness-lab \
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
harness-lab/layout_native.py measure \
/tmp/temper-buck-followup-20260910/layout/candidate-v5/candidate.kicad_pcb \
> /tmp/temper-buck-followup-20260910/layout/candidate-v5/layout-native-v5-final.json
```

The collector subprocess uses pcbnew 10.0.4 and emits a nonfatal `create wxApp before calling this` assertion on stderr while returning the complete measurement.

## Historical DRC, superseded by the corrected receipt below

Each of the three initial clean runs used the same argv, changing only the report output path:

```sh
/opt/homebrew/bin/kicad-cli pcb drc \
  --output /tmp/temper-buck-followup-20260910/layout/candidate-v5/drc-v5-1.rpt \
  /tmp/temper-buck-followup-20260910/layout/candidate-v5/candidate.kicad_pcb
```

The same command was repeated with `drc-v5-2.rpt` and `drc-v5-3.rpt`. The approved local execution path was required because the initial sandbox invocation failed before writing output with `SwiftNativeNSArray: Array index out of range`. Final runs exited 0 and each reported 0 DRC violations, 0 unconnected pads, and 0 footprint errors.

The report retained KiCad's configured ignored-check scope:

- `missing_courtyard`
- `track_not_centered_on_via`
- `tuning_profile_track_geometries`
- `footprint_filters_mismatch`
- `footprint_type_mismatch`

These exclusions were inherited from the scratch candidate project/DRC configuration; no check was added or suppressed during this follow-up.
## Corrected repository-context DRC receipt (2026-09-10)

The unchanged board was measured three times with the repository's
`_single_threaded_kicad_env()` setup and the load-bearing `--all-track-errors`
flag. The setup creates a temporary KiCad 10.0 settings tree seeded from
`/Users/bennet/Library/Preferences/kicad/10.0`, writes
`kicad_advanced` with `MaximumThreads=1`, and runs with the candidate
directory's sibling `fp-lib-table` and `fixture.pretty` available for library
resolution. The temporary settings tree is removed at process exit.

Exact Python driver argv:

```text
/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 /tmp/temper-buck-followup-20260910/layout/candidate-v5/run_pinned_drc.py
```

The three subprocess argv vectors (only output filename differs) were:

```text
/opt/homebrew/bin/kicad-cli pcb drc --all-track-errors --format json --output /tmp/temper-buck-followup-20260910/layout/candidate-v5/drc-v5-pinned-1.json /tmp/temper-buck-followup-20260910/layout/candidate-v5/candidate.kicad_pcb
/opt/homebrew/bin/kicad-cli pcb drc --all-track-errors --format json --output /tmp/temper-buck-followup-20260910/layout/candidate-v5/drc-v5-pinned-2.json /tmp/temper-buck-followup-20260910/layout/candidate-v5/candidate.kicad_pcb
/opt/homebrew/bin/kicad-cli pcb drc --all-track-errors --format json --output /tmp/temper-buck-followup-20260910/layout/candidate-v5/drc-v5-pinned-3.json /tmp/temper-buck-followup-20260910/layout/candidate-v5/candidate.kicad_pcb
```

All three exited 0 and reported zero violations, zero unconnected items,
and the same five ignored checks. The exact environment/provenance and
per-output hashes are in `pinned-drc-provenance.json`; the board SHA-256 is
`1d1ae546a0e78fe4c923b5cee736bc0811ca13a7cca33853274052f556d13ac3` and
KiCad CLI is 10.0.4. The ignored checks are `missing_courtyard`,
`track_not_centered_on_via`, `tuning_profile_track_geometries`,
`footprint_filters_mismatch`, and `footprint_type_mismatch`.
