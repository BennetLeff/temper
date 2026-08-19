# Pinned real kicad-cli DRC reports — `pcb/temper.kicad_pcb`

Three consecutive, unedited kicad-cli DRC reports for the committed board.
These are the evidence behind `tests/validation/test_drc_json_top_level_keys.py`,
which demonstrates (permanently, without needing kicad-cli at test time) that
`_drc_api._parse_drc_json` was blind to kicad-cli's top-level
`unconnected_items` array.

**Do not regenerate these to make a test pass.** They are a measurement, not a
baseline. If the board changes, the numbers below change and the test's pinned
constants must be re-measured *with an explanation attached* — that is the
whole point of pinning them.

## Conditions (state these with every number)

| condition | value |
| --- | --- |
| board | `pcb/temper.kicad_pcb` |
| board sha256 | `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` |
| measured | 2026-08-19 |
| kicad-cli | 10.0.5 |
| flags | `pcb drc --all-track-errors --format json` |
| thread pin | `KICAD_CONFIG_HOME` with `MaximumThreads=1` (`_single_threaded_kicad_env`) |
| project context | `pcb/temper.kicad_pro` resolvable (`ensure_resolvable_kicad_project`) |
| `pcb/temper.kicad_dru` | regenerated from `scripts/generate_kicad_dru.py`; 33 208 bytes, sha256 `488a01a81ea29dd6b4ed3106d3f5c0b036a9d07bf9a545a60b1ca6fbc74a0fdb` (gitignored — without it, creepage reads 0) |
| `pcb/fp-lib-table` | present beside the board (without it `lib_footprint_issues` reads exactly 168 and `lib_footprint_mismatch` reads 0) |
| `--schematic-parity` | NOT passed (this repo's `run_drc` protocol) |
| stale-extension gate | `scripts/check_stale_extensions.py` PASSED 10/10 immediately before measuring |

## What the three runs contain

All ten top-level keys kicad-cli emits, identical in all three runs:

| key | kind | count |
| --- | --- | --- |
| `violations` | array | 776 |
| `unconnected_items` | array | **339** |
| `schematic_parity` | array | 0 — because `--schematic-parity` was not passed, **not** because the board is clean |
| `ignored_checks` | array | 4 |
| `included_severities` | array | 2 (`error`, `warning`) |
| `$schema`, `coordinate_units`, `date`, `kicad_version`, `source` | scalars | — |

Per-category counts, identical across all three runs:

```
errors    clearance 179  creepage 106  hole_clearance 33  shorting_items 39
          copper_edge_clearance 11  drill_out_of_range 6  courtyards_overlap 1
          solder_mask_bridge 4      unconnected_items 339   (total 718; 379 pre-fix)
warnings  silk_overlap 199 (SATURATED — ERROR_LIMIT cap, a floor not a count)
          via_dangling 111  silk_over_copper 42  lib_footprint_mismatch 26
          lib_footprint_issues 13  missing_courtyard 5  silk_edge_clearance 1
                                                        (total 397)
```

`silk_overlap` reads exactly 199 = `ERROR_LIMIT`; it is a saturation floor.
`clearance` reads 179, which is neither 199 nor `EXTENDED_ERROR_LIMIT` (499), so
it is a real count. `unconnected_items` (499 cap) reads 339 — also a real count,
not a floor.

## What DOES differ between the three runs

The per-category counts are identical in all three. What moves is:

1. **Entry order inside `violations`.** The three files are not byte-identical
   and not even line-diff-identical after masking `date`/`uuid`: kicad-cli
   emits the same violations in a different order each run. `unconnected_items`
   order happens to be stable across these three, but do not rely on it.
   **Diff the violation SETS, not the file bytes and not the totals.**
2. **Every item `uuid`.** kicad-cli **synthesizes** them. The board file
   carries exactly **10** `(uuid ...)` tokens of its own; one report
   references **825** distinct item uuids, and only **291** recur across all
   three runs.

Keyed three ways, over these same three files:

| key | violations stable / unstable | unconnected_items stable / unstable |
| --- | --- | --- |
| item `uuid` | 310 / 1398 | 49 / 870 |
| `(type, description, item desc+x+y)` | 774 / 4 | 339 / 0 |
| `_drc_api.drc_violation_key` | **776 / 0** | **339 / 0** |

The last row is the only honest reading of a deterministic board. The middle
row's 4 "unstable" violations are the documented `shorting_items` net-order
swap (`nets A and B` vs `nets B and A`), which `drc_violation_key` normalizes;
39 of the 776 violations carry such a pair. The first row is entirely an
artefact of keying on numbers kicad-cli invented that run.
