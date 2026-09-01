<!-- provenance: commit=03d0f3697e4021f8e803c965c5424c794e767e48 dirty=true (this document only; no source, board or test file modified. All figures re-measured on 10/10 FRESH pyo3 extensions -- `check_stale_extensions.py` PASSED -- after the stale-extension episode recorded in §5.) -->

# K1's isolation barrier — the re-part worked, the placement did not, and one test cannot see either

**Date:** 2026-08-24
**Base:** `origin/main` @ `03d0f3697`
**Closes out:** [`2026-08-24-trunk-red-triage.md`](./2026-08-24-trunk-red-triage.md) §1.3

## Bottom line

Three failures in `tests/requirements/safety/test_clearance_copper.py`, and they
are three different kinds of thing:

| finding | figure | class |
|---|---|---|
| `K1` (DC_BUS) ↔ `R56` (LV_CONTROL) creepage | **5.036 mm** vs 8.0 mm enforced (PD2), 12.6 mm (PD3) | **REAL — placement** |
| `RT1` (DC_BUS) ↔ `K1` (LV_CONTROL) creepage | **7.000 mm** vs 8.0 mm | **REAL — placement** |
| `T1`, `U6`, `T2` intra-footprint blockers | — | **REAL — not investigated here** |
| `test_isolator_pad_gap[K1-13-A1-8.0]` → `KeyError: '13'` | — | **STALE TEST** |

And the finding that reframes the other three:

> **The K1 re-part succeeded. Its intra-footprint coil↔contact gap is now
> 17.800 mm, up from the 8.000 mm the test still pins.** What is left is not a
> part-selection problem. It is a placement problem, and the test that would
> have shown the improvement is the one that crashes.

## 1. K1 is a different relay now

| | OLD (`d9ab1e723`, #1225) | NOW (`03d0f3697`) |
|---|---|---|
| footprint | `temper:Relay_SPST_Omron-G4A-E` | `temper:Relay_SPST_Schrack-RT33K012` |
| origin | (95.23, 221.395) | (90, 222) |
| pads | `A1`, `A2`, `13`, `14` | `1`, `2`, `3`, `3`, `4`, `4` |

`test_isolator_pad_gap` is parameterised `[K1-13-A1-8.0]` — pad `13` to pad
`A1`, expecting 8.0 mm. Neither pad exists on the Schrack part, hence
`KeyError: '13'` at `test_clearance_copper.py:628`. **This is a stale
parameterisation, not a board defect.**

Measured on the current footprint (pure text parse of the board, no extension
involved — see §6):

```
K1 = Schrack RT33K012
  coil pads   : [('1','power_in.bypass_relay-coil1'), ('2','power_in.bypass_relay-coil2')]
  contact pads: [('4','w1_2'), ('4','w1_2'), ('3','power_in.ntc-no'), ('3','power_in.ntc-no')]

  MIN coil<->contact copper gap = 17.800 mm   (pad 1 <-> pad 4)
```

**17.800 mm against the 8.000 mm the old part gave.** The re-part more than
doubled the barrier inside the component. That is the creepage work landing, and
no test currently reports it because the one that measured it cannot find its
pads.

## 2. What is actually still violating

Authoritative, from the checker itself on fresh extensions:

```
Creepage between K1 (DC_BUS) and R56 (LV_CONTROL) is 5.036mm
Creepage between RT1 (DC_BUS) and K1 (LV_CONTROL) is 7.000mm
```

K1 appears on both sides of its own barrier — `DC_BUS` in the first, `LV_CONTROL`
in the second. That is correct, not a classifier bug: K1 *is* the barrier. Its
contact pads (`power_in.ntc-no`, `w1_2`) are mains-side; its coil pads
(`power_in.bypass_relay-coil*`) are SELV.

### 2.1 The K1↔R56 pair, verified independently

`R56` is also not the component it was. Its reference designator was reassigned
between the two revisions:

| | OLD | NOW |
|---|---|---|
| footprint | `R_1206_3216Metric` | `R_0603_1608Metric` |
| origin | (33.23, 97.29) | (119.21, 207.88) |
| nets | `+170V_BUS`, `safety.ovp.r_adc_top1-p2` (HV divider) | `+3V3`, `safety-line` (SELV) |

So the pair is new because `R56` now denotes a different part in a different
place. The geometry, computed from the board text with no extension in the loop:

```
K1.3  power_in.ntc-no  world=(115.340, 214.500)  size=(2.0, 3.0)
R56.2 safety-line      world=(119.210, 208.705)  size=(0.8, 0.95)

centre-to-centre           = 6.968 mm
rectangle edge-to-edge     = 4.549 mm
checker reports            = 5.036 mm
```

The 0.49 mm spread between my axis-aligned-rectangle figure and the checker's is
the expected direction and magnitude for rounded pad corners — the checker's true
polygon distance is *larger* than a square-cornered approximation. **The
violation is real geometry, corroborated by an independent method.**

A mains-switching relay contact ~5 mm from a 3V3 safety-interlock resistor is a
mains↔SELV barrier crossing, and it fails both the currently-enforced 8.0 mm
(PD2) and the 12.6 mm (PD3) reinforced figure.

## 3. Why the test's premise no longer fits

`test_k1_is_a_genuine_creepage_violation_after_the_400v_correction` asserts
`k1 == []` — K1 entirely clean at 8.0 mm — and its failure message points at
`test_isolator_pad_gap` for the "exact 8.000mm intra-footprint gap."

That chain is broken at both ends: the intra-footprint gap is 17.800 mm, not
8.000 mm, and the sibling test that would establish it raises `KeyError`. The
assertion conflates two separable questions:

- **Is the part adequate?** Yes, now. 17.8 mm internal.
- **Is the placement adequate?** No. 5.036 mm to `R56`, 7.000 mm to `RT1`.

A test that asks "is K1 clean" cannot distinguish them, and its name asserts a
conclusion ("after the 400v correction") about the first while failing on the
second.

## 4. Recommendation

1. **Re-parameterise `test_isolator_pad_gap` onto the Schrack pads** — coil `1`/`2`
   against contacts `3`/`4` — and re-derive the expected figure to 17.800 mm.
   This is mechanical and safe, and it restores an assertion that currently
   raises instead of measuring.
2. **Split the K1 assertion.** One test for intra-footprint isolation (part
   adequacy, now passing at 17.8 mm) and one for inter-component creepage
   (placement, genuinely red). Then the green half stops being hidden behind the
   red half.
3. **The two placement violations are owner calls.** Moving `R56` away from K1's
   contact pads, or moving K1, is a board change with its own discipline
   (`AGENTS.md`: same-PR DRC-ceiling re-measurement). Nothing here should be
   re-baselined to green.
4. `T1`/`U6`/`T2` intra-footprint blockers are a separate finding this document
   did not investigate.

## 5. A methodology failure worth recording

Everything above was re-measured on **10/10 fresh extensions**
(`check_stale_extensions.py` → `PASSED -- 10/10 extension module(s) fresh`).
It was not the first attempt.

`AGENTS.md` §"Rebuilding pyo3/maturin Rust Extensions" says:

> **A stale `.so` does not just fail — it lies.** Run the gate *before* you
> believe a number, not after a result surprises you.

I ran it after a result surprised me. At that point the gate reported **7 of 10
extensions stale**, `temper_io_types` seven days behind its source — which means
earlier local numbers in this session were taken against stale artifacts.
**Both were re-verified on fresh extensions and both hold** (the 121-test
CI-wiring claim: still `121 passed`; the tank-creepage pour finding: identical
7 failures, identical messages).

Two further traps, both documented in the same section and both hit anyway:

- `make extensions` followed by a bare `uv run` re-syncs `.venv` and evicts the
  freshly built `.so` files. The fix is `uv run --no-sync`, which that section
  states explicitly.
- `maturin develop` reported `Finished in 0.04s` and warned
  `Couldn't find the symbol PyInit_temper_geometry`, because
  `target-shared/release/libtemper_geometry.so` was a cached artifact built
  **without** the `python` feature (the wasm tier builds that crate
  `--no-default-features`). `cargo clean -p` did not clear it. Removing that file
  directly and re-running produced a real `Compiling temper-geometry` and a
  working module.

The local venv is now healthier than at session start (10/10 fresh vs 7 stale),
but it passed through a state where `temper_geometry` was unloadable. Anyone
seeing that symptom: check `nm -D <installed .so> | grep -c PyInit` and the
shared target dir before assuming a source problem.

## 6. Reproducing

```bash
uv run --no-sync python scripts/check_stale_extensions.py     # do this FIRST
cd packages/temper-placer
uv run --no-sync pytest tests/requirements/safety/test_clearance_copper.py -q --tb=line

# the two violations, verbatim
uv run --no-sync pytest "tests/requirements/safety/test_clearance_copper.py::TestRealBoardIsolatorFigures::test_k1_is_a_genuine_creepage_violation_after_the_400v_correction" \
  -q --tb=long | grep -oE "Creepage between [A-Z0-9]+ \([A-Z_]+\) and [A-Z0-9]+ \([A-Z_]+\) is [0-9.]+mm" | sort -u
```

The §1 and §2.1 geometry is a standalone text parse of `pcb/temper.kicad_pcb`
(footprint block → pad `(at …)` rotated into world coordinates → rectangle
edge distance) and needs no extension; the script is in this session's transcript
and reproduces the 17.800 mm, 6.968 mm and 4.549 mm figures.

## 7. Sources

- `packages/temper-placer/tests/requirements/safety/test_clearance_copper.py:628, 674` — the two failing assertions.
- `pcb/temper.kicad_pcb` — K1 and R56 footprint blocks.
- `AGENTS.md` §"Rebuilding pyo3/maturin Rust Extensions" — §5's warning, and `docs/evidence/2026-08-11-worktree-poisons-shared-venv.md` behind it.
- `docs/evidence/2026-08-24-trunk-red-triage.md` §1.3 — the triage entry this closes.
