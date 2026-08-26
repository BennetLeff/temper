<!-- provenance: commit=91b65e8a59a22ef6567e2ff8e04539a992935651 dirty=false (the 120-sample DRC campaign and exact-copper measurement were taken on this clean commit; this evidence file and the ceiling update were authored afterward from those recorded results) -->

# Clear C27's actionable creepage pairs by moving its SELV counterparts

**Date:** 2026-08-26

**Board commit measured:** `91b65e8a59a22ef6567e2ff8e04539a992935651`

**Board SHA-256:** `7c8b26d3d812fd0d07e29ee404a2723c22d276ece19adf0fc67fb95547984065`

## Result

Move the two small SELV counterparts instead of the 40 mm, high-current tank
capacitor:

| Ref | Before | After | Delta |
|---|---:|---:|---:|
| `U21` | `(80.22, 246.20)` | `(85.22, 246.20)` | `+5.0 mm X` |
| `R48` | `(84.41, 242.27)` | `(85.41, 242.27)` | `+1.0 mm X` |

`C27` and its tank copper do not move. Neither moved footprint had a routed
track endpoint at its pad coordinates on the committed board, so the
position-only edit does not detach routed copper.

The exact-copper cross-domain instrument measured all 26,640 HV-to-SELV pad
pairs with KiCad's externally-oracled `R(-theta)` convention:

| Classification | Before | After | Delta |
|---|---:|---:|---:|
| all pairs below 12.6 mm | 97 | 93 | -4 |
| `body_free` | 8 | 5 | -3 |
| `body_crossing` | 88 | 87 | -1 |
| unknown body | 1 | 1 | 0 |

The removed pairs are exactly:

- `C27.2(tank.c_tank1-p2)` ↔ `U21.4(gnd)` (`body_free`)
- `C27.2(tank.c_tank1-p2)` ↔ `U21.5(+3V3)` (`body_free`)
- `C27.2(tank.c_tank1-p2)` ↔ `R48.2(safety.ovp.comp-inp)` (`body_free`)
- `C27.2(tank.c_tank1-p2)` ↔ `U21.2(gnd)` (`body_crossing`)

No new pair appears. The first three are the three `C27` actionables named by
`2026-08-25-hv-selv-creepage-burndown-list.md`; actionable work therefore
falls from eight pairs across four HV-side references to five pairs across
three. The earlier document's prose says "five components," but its complete
eight-row table names only `C27`, `C14`, `R4`, and `R23`; four is the
table-derived count, not a new classification made here.

## Independent KiCad DRC measurement

Instrument setup was checked before measurement:

- regenerated `pcb/temper.kicad_dru` from its SSOT;
- `scripts/check_stale_extensions.py`: 10/10 fresh;
- `kicad-cli version`: 10.0.5;
- `temper_placer.validation._drc_api.run_drc`, which supplies
  `--all-track-errors` and the single-thread KiCad environment;
- clean tree at the measured commit;
- 120 samples.

Every category had spread zero:

| | Before ceiling | Observed, 120/120 | New ceiling |
|---|---:|---:|---:|
| total errors | 413 | 409 | 409 |
| creepage | 107 | 103 | 103 |
| total raw warnings | — | 402 | — |

Every other error category is unchanged. The four-error decrease is entirely
creepage, agreeing with the independent exact-copper set delta.

`silk_over_copper` is 45/45 in all 120 candidate samples and also 45 in an
exact parent-board control. The prior ceiling retained 46 even though its own
2026-08-25 march entry said the measured value was 45. The warning ceiling is
therefore tightened by one as inherited slack, not attributed to this move.
The uncapped `silk_overlap=13061` total is unchanged; neither moved footprint
is `C2` or `C3`, the documented dominant saturated pair.

No ceiling rises. `ci_check_drc.py --backend kicad-cli` passes the DRC,
cap-saturation, and noise-headroom guards.

## Remaining work

The remaining actionable `body_free` pairs are the `R23`, `C14`, and `R4`
groups from the 2026-08-25 list. The 87 `body_crossing` findings remain
blocked on the Annex L certification-lab question; this move makes no claim
about them.
