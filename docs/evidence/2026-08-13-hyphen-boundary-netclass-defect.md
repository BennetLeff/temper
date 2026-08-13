<!-- provenance: commit=a3fbaff37afd739b72f2b109847813b30ceb8e88 dirty=true -->

# Hyphen-boundary net-classification defect: root cause, blast radius, fix

Branch `fix/hyphen-netclass-boundary`, branched from
`origin/fix/board-schematic-resync` (base commit `a3fbaff37`, own worktree
`/home/bennet/Desktop/temper-hyphen-netclass-fix`). `make venv-isolate`;
`scripts/check_stale_extensions.py` 10/10 fresh + explicit
`importlib.import_module` on the two touched extensions
(`temper_io_types`, `temper_design_bundle_python`) confirmed loadable,
before and after every measurement below. `scripts/check_venv_integrity.py`
PASSED, all 18 entries. `make netlist` run fresh in this worktree;
`elec/build/default.net.source-digest`: `8cfd715e60a3b8e22313562d8afed4ba48f54f096f73ef52d8f573bb378bea6a`.

Coordinates with PR #1145 (`fix/hb-gnd-domain-classification-1786647794`,
open, base `fix/board-schematic-resync`): that PR declares `hb-gnd` (HV),
`s1` and `I_SENSE` (SELV) in `elec/domain_manifest.yaml` — a correct,
complementary fix that this branch does not duplicate. This branch was cut
before #1145 merges, so every measurement below reflects a manifest that
does **not** yet declare `hb-gnd`/`s1`/`I_SENSE`; see "Residual risk"
below for what changes once #1145 lands.

## 1. Root cause

`temper_placer.core.net_classification.is_ground_net` (`net_classification.py:95`)
delegates to `temper_io_types.is_ground_net` (pyo3), implemented in
`packages/temper-io-types/src/placer_core/netclass.rs::pattern_source`.
Before this fix:

```rust
format!(r"(?:\A|_){escaped}(?:\z|[\d_])")
```

Word boundary = `_` or start/end of string, **only**. `-` was never a
boundary character, anywhere in this pattern's history.

```
$ is_ground_net("hb_gnd")  -> True
$ is_ground_net("hb-gnd")  -> False
$ is_ground_net("a_gnd")   -> True
$ is_ground_net("a-gnd")   -> False
$ is_ground_net("dc-gnd")  -> False
$ is_ground_net("DGND")    -> True   (start-anchored; unaffected)
```

### One regex, or a family?

**A family**, all independently maintained, all sharing the identical
`(?:^|_){kw}(?:$|[\d_])` shape (Python) / `(?:\A|_){kw}(?:\z|[\d_])` (Rust) —
this repo's own convention of verifying each copy independently rather than
unifying them (documented in each module's own docstring: "must not
silently converge") means the identical bug had to exist, and be found,
independently in each copy. Located by grepping the repo for the literal
`(?:^|_)` / `(?:\A|_)` shape:

**Family A — the net/pin-name classifier `is_ground_net` belongs to**
(`temper_io_types::placer_core::netclass`, one shared `matches_any`/
`pattern_source` function used by all eight `PatternSet` variants; the two
Python call sites, `core/net_classification.py` and
`router_v6/net_classification.py`, each keep an unused-in-production
`_matches_any` as the pinned statement of the matching rule the Rust port
reproduces). **FIXED in this PR**, scoped to the four *net-name* pattern
sets (`GroundNet`/`PowerNet`/`HvNet`/`PowerNetV6` — what `is_ground_net`/
`is_power_net`/`is_hv_net`/`is_power_net_v6` use). The four *pin-name*
pattern sets keep the original `_`-only boundary (see §5).

**Family B — the `DesignRules.get_rules_for_net` pattern cascade**
(`temper-design-bundle`'s `design_rules.rs::hv_word_boundary_match`, ported
from a *different*, independently-verified Python function,
`_design_rules_py_oracle.py::_hv_word_boundary_match`). Same shape, same
bug, same fix. Drives `is_gate_net_hv`/`is_gate_net_selv`/
`is_high_current_net` — three more tiers of the exact cascade that put
`hb-gnd` on `Default`. **FIXED in this PR** (with a mitigation for one
keyword — see §3).

**Family C — NOT fixed in this PR, reported as blast radius:**
- `router_v6/clearance_check.py::_is_hv_keyword_match`/`_classify_net_class`
  (own `_CLASSIFY_HV_KEYWORDS` tuple, own regex).
- `router_v6/creepage_check.py::_is_high_voltage_net`, delegating to
  `temper-geometry`'s `creepage_check.rs`.
- `router_v6/clearance_engine.py::_kw_boundary_match`/
  `_net_class_to_voltage_class`, delegating to `temper-geometry`'s
  `via_clearance.rs::kw_boundary_match`.
- `router_v6/trace_width_assignment.py`'s Rust port,
  `temper-geometry/src/trace_width_assignment.rs::kw_boundary_match_impl`.
- `core/design_rules.py`'s **module-level docstring already documents**
  three of these five as the earlier-fixed (2026-07-27/28) instances of
  the *substring* defect class — this PR fixes a *different* axis
  (boundary character set) of the *same* underlying regex shape in the
  two families above, and leaves this third family's *boundary character
  set* unaudited. All five are confirmed, by direct code read, to use the
  identical `(?:^|_)…(?:$|[\d_])` shape and therefore share the identical
  hyphen-blind-spot — not verified net-by-net against the board the way
  Families A/B are in §2 below, since they gate a genuinely different
  subsystem (real-time router/DRC clearance decisions during
  placement/routing, not `DesignRules.get_rules_for_net`'s net-class
  table) and fixing them is a separately-scoped, separately-verified
  change, consistent with this repo's own established one-fix-at-a-time
  discipline for this defect class (`docs/evidence/2026-07-27-net-classification-gate.md`,
  `docs/evidence/2026-07-28-zone-layer-classification-fix.md`).
- Three more non-delegating production call sites with their own inline
  copy of the same regex, same `_`-only boundary, not audited here:
  `_constraint_types/config.py::DesignRulesConfig.get_net_class` (lines
  450/461), `io/_parse_board.py`'s plane-eligibility fallback (line 83),
  `router_v6/constraints_design_rules.py`'s zone-clearance HV check (line
  445).

## 2. Blast radius: all 85 hyphenated nets

`elec/build/default.net` (fresh, this worktree): **162 nets total, 85
contain a hyphen** (confirmed: `grep -oP '\(net \(code "\d+"\) \(name "\K[^"]+'
elec/build/default.net | sort -u`, filtered in Python for `'-' in name`).

**Board-wide simulation (all 162 nets, not just the 85 sampled by
inspection) of exactly which classifications the widened boundary flips**,
cross-checked against every hyphenated net's `elec/domain_manifest.yaml`
declaration where one exists:

| Net | Family | Before | After | Manifest domain | Verdict |
|---|---|---|---|---|---|
| `hb-gnd` | A (`is_ground_net`) | `False` | `True` → `GND` class | **Undeclared** (declared HV by open PR #1145) | **The intended fix** — see "Residual risk" below: `GND` class is still not the *correct* class for this HV-domain net; a Tier-2 override is the real fix, out of this PR's scope (§ Residual risk). |
| `hb.gate_hs-vdd` | A (`is_power_net`) | `False` | `True` → `Power` class | Undeclared | **0 pads** (`grep` of `elec/build/default.net`: net code 53, zero `(node ...)` entries — a phantom/unconnected net). Genuinely ambiguous name (VDD is ambiguous LV-logic-supply vs. this chip's own HV-referenced isolated bias rail — see domain_manifest's adjacent `hb.gate_hs.driver-p1-1`/`-p2` entries for the same physical driver). Zero live safety consequence today (no copper); flagged for explicit declaration if this net ever gains pads. |
| `hb.gate_ls-vdd` | A (`is_power_net`) | `False` | `True` → `Power` class | Undeclared | Same as above (net code 54, 0 pads). |
| `discharge.k_dis1-coil1` | B (`is_high_current_net`, `"COIL"`) | `False` (→ `Default`) | `True` → would be `HighCurrent` (`safety_category="HV"`) | **SELV** (`elec/domain_manifest.yaml`: "SELV coil drive") | **Over-match, mitigated** — see §3. Resolves to `Signal` (explicit Tier-2 override added this PR), not `HighCurrent`. |
| `discharge.k_dis1-coil2` | B | `False` | `True` (same) | SELV | Same mitigation. |
| `discharge.k_dis2-coil1` | B | `False` | `True` (same) | SELV | Same mitigation. |
| `power_in.bypass_relay-coil1` | B | `False` | `True` (same) | SELV | Same mitigation. |
| `power_in.bypass_relay-coil2` | B | `False` | `True` (same) | SELV | Same mitigation. |
| every other of the 85 | A and B | no change | no change | 8 HV / 7 SELV / 70 undeclared | Unaffected — see below. |

**Zero other flips exist board-wide** (all 162 compiled net names, not
just the 85 hyphenated ones — the Rust test `full_board_hyphenated_net_scan`
in `packages/temper-io-types/src/placer_core/netclass.rs` pins this exact
set and fails if it ever drifts). In particular `is_hv_net` (the
`AC_L`/`AC_N`/`PE`/`DC_BUS+`/`DC_BUS-`/`SW_NODE` family) has **zero**
flips anywhere on the board, and the `GATE`/`SW_NODE`/`PWM`/`DC_BUS`/
`AC_L`/`AC_N` keywords in Family B also have zero flips — `"COIL"` is the
**only** over-match-prone keyword found across both families, on this
board's actual net names.

### How many of the 85 land on `Default` (`creepage_mm = 0.0`) today?

**77 of 85** (measured: `create_temper_design_rules().get_class_for_net(net)
== "Default"` for each of the 85, `.venv/bin/python` against the freshly
rebuilt extension). Of those 77: **0 are declared HV** in
`elec/domain_manifest.yaml` (all 8 manifest-HV hyphenated nets already
carry an explicit `TEMPER_NET_ASSIGNMENTS` entry — `discharge.k_dis1-nc`,
`discharge.k_dis2-nc`, `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`,
`hb.power_loop.q_high-g`, `power_in.ntc-no`, `tank-out`,
`tank.c_tank1-p2`), 7 are SELV, 70 are undeclared in the manifest either
way (ordinary SELV-adjacent control-logic signals — safety interlock fault
lines, RTD sensing, MCU voltage references, relay-drive gate signals —
none of which the pattern cascade or the manifest currently has any
opinion on, and none of which this fix's boundary widening touches).

**This is why the live number is 0, not something larger, on *this*
branch** — not because the defect is harmless, but because every
hyphenated net whose manifest-HV status is *currently* declared already
has a hand-maintained Tier-2 override that bypasses the broken pattern
cascade entirely. `hb-gnd` is exactly the counter-example: PR #1145
(open, not yet merged into this branch's base) is in the process of
adding its manifest declaration, and design_rules.py's own change history
(the `+170V_BUS`, `+15V_LS`, `"a"`, `w1_1`/`w1_2`, `zcd`, `tank-out`,
`hb.power_loop.q_high-g`, `hb.gate_hs.driver-p1-1`/`-p2`,
`power_in.ntc-no` entries — 5 separate "ADDED ... coverage gap" comments in
that one table, covering these 9+ net names, `grep -c "# ADDED "
design_rules.py`) shows this table has repeatedly, historically lagged
the manifest by exactly this kind of omission. **`scripts/check_hv_netclass_coverage.py`
PROPERTY 1 exists to catch a manifest-HV net missing from
`TEMPER_NET_ASSIGNMENTS`** — but it says nothing about whether the
*pattern-cascade fallback* (the thing that's supposed to catch such a
miss) is itself blind to half the board's net names. That is what this
fix closes: **the safety net for the safety net.**

## 3. The `"COIL"` over-match, and why it's fixed by declaration, not by narrowing the boundary

Widening Family B's boundary uniformly (`GATE`, `SW_NODE`, `PWM`,
`DC_BUS`, `AC_L`, `AC_N`, `COIL`) would, left alone, reclassify five real,
confirmed-SELV relay-coil-drive nets (`discharge.k_dis1-coil1`/`-coil2`,
`discharge.k_dis2-coil1`, `power_in.bypass_relay-coil1`/`-coil2`) from
`Default` to `HighCurrent` (`safety_category = "HV"`) — the identical
false-positive shape `creepage_check.py`'s 2026-07-27 fix already fought to
remove for these same five nets, under a *different* mechanism
(`creepage_check.py`'s own `broad_keywords`, Family C above, still
correctly excludes them today — confirmed by
`test_is_high_voltage_net_rejects_known_false_positives`, unaffected by
this PR since Family C is untouched).

Narrowing the fix back down for just `"COIL"` was rejected: it would
special-case one keyword today and silently reintroduce this exact defect
for the next hyphenated `COIL`-adjacent (or any other keyword-adjacent) net
tomorrow — precisely the "same bug, found a fourth/fifth/sixth time" shape
this repo's `check_net_classification.py` docstring already documents at
length. Instead, `packages/temper-placer/src/temper_placer/core/design_rules.py`'s
`TEMPER_NET_ASSIGNMENTS` (Tier 2, wins over the Tier 4+ pattern cascade)
gains five explicit entries mapping these nets to `"Signal"` — numerically
identical to what they already resolved to (`Default`: trace_width 0.2mm,
clearance 0.15mm, creepage_mm 0.0), but now immune to any future pattern
change, with an explicit `safety_category="LV"` recorded. This mirrors the
established remediation pattern this exact table already uses nine times
over (§2).

## 4. Verification

- `packages/temper-io-types/src/placer_core/netclass.rs`: 16/16 unit tests
  pass (`cargo test --manifest-path packages/temper-io-types/Cargo.toml --lib`),
  including four new tests (`hyphen_is_now_a_net_name_boundary`,
  `hyphen_boundary_does_not_over_match`,
  `pin_name_boundary_is_unchanged_by_the_net_name_fix`,
  `full_board_hyphenated_net_scan` — the last pins the exact 3-flip,
  board-wide set from §2). Full crate suite: 7014/7014 pass.
- `packages/temper-design-bundle/src/design_rules.rs`: `cargo build
  --features python` and `cargo clippy --all-features -- -D warnings` both
  clean. `cargo test --features python` cannot link for this crate
  (`extension-module` pyo3 feature — a pre-existing, structural limitation:
  CI dropped `cargo test` for this exact crate on 2026-08-11, and this
  crate's `#[cfg(test)]` modules are not wired into the `wasm-registry`
  tier either, confirmed by `grep design_rules
  packages/temper-design-bundle/src/wasm_test_registry.rs` returning
  nothing — these Rust-level unit tests have had no execution path since
  before this PR; not a regression this PR introduces). Verified instead
  through the real compiled `.so` via the Python differential/PBT suites
  below, which is this crate's actual, CI-exercised verification path for
  `design_rules.rs`.
- Python, against the freshly rebuilt `temper_io_types` +
  `temper_design_bundle_python` extensions (10/10 fresh, both explicitly
  import-checked before AND after):
  - `test_design_rules_pbt.py`: 13/13 (updated `_wb_ref`, `_NET_ALPHABET`,
    and `test_p3_fails_for_plain_substring`'s falsifier net name — see
    inline comments for why each changed).
  - `test_design_rules_rust_differential.py`: 26/29 pass. **3 pre-existing
    failures, confirmed unrelated** (reproduce identically with this PR's
    diff fully reverted, `git stash`): `_design_rules_py_oracle.py` is
    frozen at commit `e5bd461e2`, predating an already-landed,
    already-on-this-branch reassignment of `TEMPER_NET_ASSIGNMENTS["gnd"]`
    (`"GND"` → `"Power"`) and `["PWR_RTN"]` (`"GND"` → `"HighVoltage"`)
    that the oracle was never re-pinned for. Not this PR's defect, not
    fixed here (fixing it requires verifying an unrelated, already-landed
    change this PR did not make); this PR's own 5 new
    `TEMPER_NET_ASSIGNMENTS` entries ARE mirrored into the oracle (§3) and
    introduce zero additional divergence (confirmed: `Omitting 57
    identical items` after this PR's changes vs. `Omitting 52` before,
    with the same 2 `Differing items` in both).
  - `test_net_classification.py` (core): 34/34.
  - `test_net_classification_rust_differential.py` (router_v6): 15/15
    (updated the three net-level oracle helper calls to pass
    `boundary="_-"`; the pin-level ones and the 500-name deterministic
    random-fuzz sweep, seed `20260807`, contain zero hyphens and are
    unaffected either way).
  - `test_core_contracts_differential.py` (R1a, the *frozen-at-commit*
    `_core_py_oracle.py` — deliberately **not** edited, see its own
    "DO NOT EDIT" / "moves the goalposts" docstring): **910/910 pass,
    unmodified.** Its 5102-name corpus (systematic + a seed-`20260804`,
    4500-name random fuzz over an alphabet that includes `-`) was checked
    net-by-net for divergence before writing any code — **zero** names in
    that corpus straddle a hyphen-adjacent keyword boundary, so this
    file's contract (Rust ≡ the frozen pre-migration snapshot) holds by
    coincidence of what that corpus happens to contain, not because the
    defect doesn't apply to it.
  - `test_coverage_paydown_wave7a.py` (`_matches_any` direct calls): 2/2.
  - Family C (untouched, sanity-checked unaffected):
    `test_creepage_check.py` + `test_creepage_check_rust_differential.py`:
    60/60.
  - `packages/temper-placer/tests/core/`: full-directory runs land at
    3110-3111/3123 pass across repeated runs, 6 skipped, with 6-7
    failures — 6 stable and reproduced with this PR's diff fully reverted
    (`test_apply_net_class_mapping_strict.py` x2 — "ac_l" case-sensitivity
    against the real netlist; `test_coverage_paydown_v9.py::test_get_version`
    — kicad-cli environment; the 3 `test_design_rules_rust_differential.py`
    ones above), plus one intermittent, `test_net_types_pbt.py::
    test_mr1_round_trip_and_kwarg_order_commute` — a Hypothesis
    property-based test over `core/net_types.py`'s `NetTypeSpec`
    (differential-pair trace-width modeling), a module and file this PR's
    diff never touches (`git diff --stat` lists 8 changed files, neither
    `net_types.py` nor its test); its own falsifying example is a
    default-valued vacuity-guard edge case
    (`max_current_a=0.5, creepage_mm=0.0, prefer_short_stubs=True`, the
    exact values the guard assertion excludes), consistent with
    Hypothesis example-database flakiness rather than a real regression.
  - `packages/temper-placer/tests/router_v6/`: broad sweep, every failure
    sampled (`test_channel_skeleton_*` — `networkx.Graph` has no
    `is_connected` in this environment's installed version;
    `test_kicad7_footprint_dir_resolves` — `KICAD7_FOOTPRINT_DIR` unset in
    this worktree; `test_latency_unroutable_early_exit` — a 20ms timing
    threshold, 34.5ms measured, flaky under this session's concurrent-agent
    CPU contention) confirmed to reproduce identically with this PR's diff
    fully reverted (`git stash`) — none touch net classification.
- `scripts/check_net_classification.py`: **PASSED** (unaffected by
  design — its own docstring: "does not attempt to also validate
  word-boundary-ness of an already-anchored regex", so this defect class
  is out of that gate's scope by construction; it audits for bare
  substring `in` tests, not boundary-character correctness).
- `scripts/check_hv_netclass_coverage.py`: **PASSED**, 0 violations
  (PROPERTY 1/2/3/4 all clean) — unchanged from before this PR, since
  `hb-gnd`/`s1`/`I_SENSE` are not yet manifest-declared on this branch
  (§ Residual risk).
- `git status --porcelain` / `git grep -l "^<<<<<<< "`: clean.

## 5. What was deliberately NOT widened

The four *pin-name* pattern sets (`GroundPin`/`PowerPin`/`HvPin`/
`ClockPin`) keep the original `_`-only boundary. Schematic pin names in
this repo's convention (`GND`, `VCC`, `A0`, differential-pair `D+`/`D-`,
...) were not audited for real hyphenated instances the way the 162
compiled net names were for this fix — widening them without that audit
risks introducing an unverified over-match on the pin side, mirroring
exactly the `"COIL"` risk in §3 but without a corresponding board-wide
check to catch it. Left as a documented, separate follow-up
(`PatternSet::boundary_chars`'s doc comment in `netclass.rs` records this
explicitly).

## 6. Residual risk — the fix is necessary, not sufficient, for `hb-gnd`

`hb-gnd`'s own name is misleading: it contains the substring "gnd" but is
electrically the half-bridge low-side return, ~-170V, one CT-primary
splice from `DC_BUS_RTN` (per PR #1145's own wire-tracing). This fix makes
`is_ground_net("hb-gnd")` correctly agree with `is_ground_net("hb_gnd")` —
but the *pattern* it agrees on is still just the literal substring "gnd",
which cannot know that *this particular* "gnd" is a HV-domain node, not a
SELV one. Measured, before vs. after this fix, still with no
`TEMPER_NET_ASSIGNMENTS` entry for `hb-gnd` (none added by this PR — see
"Coordinates with PR #1145" above):

| | `get_class_for_net("hb-gnd")` | `clearance` | `creepage_mm` |
|---|---|---|---|
| Before this fix | `Default` | 0.15mm | **0.0mm** |
| After this fix | `GND` | 0.3mm | **0.0mm** |
| Needed (matches PR #1145's HV declaration) | `HighVoltage` (or a project-specific HV subclass, per the same voltage/current-tier reasoning already applied to `HighVoltageSignal`/`HighVoltageTank`) | 2.0mm | **6.0mm** |

This fix is a **strict improvement** (stricter clearance, and — critically —
`is_ground_net`/`is_power_net`/`is_hv_net` no longer silently disagree
depending on whether a net happens to use `_` or `-`) but does **not**, by
itself, give `hb-gnd` correct HV creepage enforcement in
`DesignRules.get_rules_for_net`. That requires an explicit
`TEMPER_NET_ASSIGNMENTS` entry — the same Tier-2-beats-pattern-cascade
technique already used nine times in that table (§2) and the same
technique this PR uses for the five `"COIL"` nets (§3) — which is
deliberately **not** added here, per the coordination note: PR #1145 owns
`hb-gnd`'s manifest declaration, and a `design_rules.py` entry should
follow it (not precede it), the same way PR #1145 itself already flags
`TEMPER_NET_ASSIGNMENTS`/`pcb/temper.kicad_pro` as its own explicit,
out-of-scope follow-up. **Recommended next step, once PR #1145 merges**:
add `"hb-gnd"` (and `s1`/`I_SENSE` if their own name-pattern resolution
needs it — not checked here, out of this fix's scope) to
`TEMPER_NET_ASSIGNMENTS`, choosing its class with the same voltage/current
derivation already on record for this board's other HV subclasses.

## 7. Nets genuinely ambiguous from their name alone

Per the task's own framing: a net whose correct class cannot be determined
from its name belongs in an explicit declaration, not a pattern. Two
found by this fix's own blast-radius scan:

- **`hb.gate_hs-vdd`**, **`hb.gate_ls-vdd`** — 0 pads each (verified:
  `elec/build/default.net` net codes 53/54, zero `(node ...)` entries).
  "VDD" is genuinely ambiguous in this design (ordinary LV logic supply
  in most contexts; this specific driver's own isolated HV-referenced
  bias rail in others — see `hb.gate_hs.driver-p1-1`/`-p2`, the *same*
  physical chip's already-manifest-declared HV bias pins). Zero live
  safety consequence today (no copper to protect), so not urgent, but
  flagged rather than silently left to whatever the pattern cascade
  happens to resolve (`Power`, after this fix) if these nets ever gain
  real pads in a future placement pass.
- **`hb-gnd`** itself, per §6 — the manifest declaration is in flight
  (PR #1145); the `design_rules.py` class assignment is not, and should
  not be guessed from the name "hb-gnd" alone once that declaration lands.
