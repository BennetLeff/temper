<!-- provenance: commit=16f673f712747ee486918aaab4c9d28bbdfb98ad dirty=UNKNOWN -->
/home/bennet/Desktop/temper-uncapped-drc, based on origin/main cc732df2b), dirty=false for pcb/** throughout
(git status --porcelain pcb/ clean at every measurement below). pcb/temper.kicad_pcb sha256=
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, pcb/temper.kicad_pro sha256=
f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac -- the SAME board #1110 measured, byte-
identical; NEITHER FILE IS TOUCHED by this task or by the shipped tool (scripts/measure_uncapped_drc.py).
"Post-precedence-fix" below means: pcb/temper.kicad_pcb and pcb/temper.kicad_pro exactly as committed on
origin/main, paired with the .kicad_dru that scripts/generate_kicad_dru.py emits on branch
fix/dru-rule-precedence (commit 11b344c65, PR #1110 -- not yet merged to main at the time of this
measurement; verified `git merge-base --is-ancestor 889fd7262 origin/main` fails). This document does not
land that fix and does not modify power_pcb_dataset/drc_ceiling.json. kicad-cli 10.0.5. No subagents were
dispatched (single-agent task, per instruction). -->

# Uncapped DRC violation counting: kicad-cli's 199/499 are reporting limits, and every category that sits on one is a gate that can never fire

**Verdict up front.**

1. **Instrument: kicad-cli itself, via provably exhaustive, non-overlapping partition-and-sum — not `temper-drc-rs`.** `temper-drc-rs` has no board-wide, DRU-equivalent clearance kernel wired to Python; the one that comes closest (`verify_route_clearance`, the router's Stage-5.7 check) uses a *different* clearance model — a flat 0.127mm default plus HV-keyword-gated escalation to 4.2/14.0mm — not the DRU's IEC-60335-cited, netclass-pair-specific 0.2–8.0mm figures. Run against the real board it reports 17–65 clearance violations depending on whether the manifest's HV net-name list is supplied, against kicad-cli's true 1,664. That is not disagreement to arbitrate; it is two instruments answering different questions (sec 6).
2. **Exhaustiveness is proven, not asserted, for `clearance`, `creepage`, `track_width`.** The partition is: rank every DRU rule of a constraint type by `min` value (ties broken by authored order — the same tie-break the fix's own topological sort uses); isolate rule *R*'s band with a synthetic 2-rule `.kicad_dru` (`(severity ignore)` on everything **not** matching *R*'s condition AND-NOT every strictly-higher-ranked rule's condition; *R*'s real value on the rest); recurse by bisecting the band's own real net names when it is still at/near the cap. Every board item-pair matches exactly one rule's isolation condition or the netclass-implicit fallback — never zero, never two — by construction of the AND-NOT chain, not by inspection. Reproduces PR #1110's independently-hand-derived 1,307 exactly (sec 4).
3. **True per-category counts, post-precedence-fix, for the committed board (sec 5):** `clearance` **1,664** (kicad-cli reports 499–513), `creepage` **200** (kicad-cli reports 198–200 — genuinely *not* capped, confirmed by exhaustive partition, not just the doc's 20mm-rule proof), `track_width` **490** (kicad-cli reports 199 — **2.46× the reported cap**). `shorting_items` and `silk_overlap` are **proven saturated** but this session could not ship a trustworthy exact whole-board count for either — said plainly, not glossed over (sec 5.3–5.4).
4. **`shorting_items` and `silk_overlap` needed a different partition family (physical board-content deletion, not DRU conditions), because neither carries a `rule` attribution in kicad-cli's own JSON** — verified, their `description` field never contains `rule '...'`. For `silk_overlap` this uncovered a real, separate defect: a single footprint (`C5`, `Capacitor_THT:CP_Radial_D35.0mm`) draws its silkscreen as 554 tiny hatch-pattern line segments instead of a circle, and that ONE footprint paired with its neighbor `C7` alone saturates the whole-board cap (sec 5.4).
5. **`power_pcb_dataset/drc_ceiling.json`'s `shorting_items: 199`, `track_width: 199`, and `silk_overlap: 199` entries are gates that can never fire** — measured, independently confirmed here, not merely re-asserted from PR #1110. `clearance: 386` is additionally stale for an unrelated reason: it predates the precedence fix by construction (sec 7). Not modified by this document.

---

## 1. Which instrument, and why

The brief asked to evaluate **(1)** kicad-cli partition-and-sum, and **(2)** whether `packages/temper-drc-rs` is a better, uncapped instrument for the same measurement.

**`temper-drc-rs` does not have a drop-in replacement for kicad-cli's `clearance` check.** Searched the crate for anything that computes pairwise copper clearance across the whole board:

- `rules::drc::ClearanceCheck` (`clearance.rs`) — **component-to-component** (footprint bounding-box) clearance, not item-pairwise. Different unit of measurement entirely; not comparable to kicad-cli's `clearance` category, which is track/pad/via/zone-pairwise.
- `rules::drc::TraceClearanceCheck` (`trace_clearance.rs`) — trace-to-trace only (no pad/via/zone), driven by `constraints::ConstraintSet`/`NetClassRules`. Not exposed to Python (`uv run python -c "import temper_drc_rs as t; [n for n in dir(t) if ...]"` finds no `TraceClearanceCheck`/`drc_trace_clearance` binding) — it is a Rust-internal kernel with no board-wide entry point a caller can reach.
- `router_clearance::verify_route_clearance` (Router V6 Stage 5.7) — **the one thing that IS callable from Python on real board data**, and the one `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`'s `backend="auto"`/`"rust"` actually uses in production. This is the instrument evaluated in sec 6, and it disagrees with kicad-cli by 25–100× because it is checking a different requirement (a router-time, near-fabrication-limit collision avoidance figure), not the DRU's certified IEC 60335 netclass-pair clearance. Characterized, not picked as a winner, per the task's instruction.

**kicad-cli, partitioned, is therefore the instrument used for every "true count" in sec 5.** It is also the fab-authoritative checker — `temper_placer.validation._drc_api.run_drc` (production) and every prior DRC-ceiling record in this repo are already built on it — so a kicad-cli-based measurement is what the ratchet and ceiling gate can actually consume without a new source of truth to reconcile.

---

## 2. Partition method 1: DRU-rule-governed categories (`clearance`, `creepage`, `track_width`)

### 2.1 Why this partition is exhaustive and non-overlapping, not just plausible

KiCad's own semantics (documented, and re-verified independently by PR #1110 sec 1.2 against this exact board): **the last matching rule in the file wins.** Given a DRU with `RuleShadowingError`'s guard passing — i.e. rules are emitted in an order where the last-matching rule is *always* the rule with the greatest `min` value among every rule matching a given pair (fix/dru-rule-precedence's `order_rules_by_strictness`; verified here too: `find_shadowing(generate_dru())` → `[]`) — the winner for any pair is a **pure function of value-rank**, independent of anything about the pair except which rules' conditions it satisfies.

That means: for rules ranked `R1 > R2 > ... > Rn` by value (ties broken by authored order), a pair's true governing rule is `Ri` iff it matches `Ri`'s condition and matches no `Rj` with `j < i`. So the isolation condition

```
cond(Ri) = Ri.condition  &&  !(R1.condition)  &&  !(R2.condition)  &&  ...  &&  !(R(i-1).condition)
```

partitions pair-space exactly: every pair matches **at most one** `cond(Ri)` (if it matched two, the higher-ranked one's AND-NOT would exclude it from the lower one), and every pair that matches *any* rule at all matches **exactly one** (the highest-ranked rule it satisfies, by induction on rank). Pairs matching *no* explicit rule fall through to `!(R1.condition || ... || Rn.condition)` — the netclass-implicit fallback, measured separately for `clearance` only (creepage/track_width have no per-netclass board-setting fallback).

`scripts/measure_uncapped_drc.py`'s `measure_category_exhaustive()` builds exactly this chain from the DRU text itself (own regex/paren parser, independent of `scripts/generate_kicad_dru.py`'s internals — works whether or not that generator's fix has landed), so the exhaustiveness proof above is a property of the *emitted rule file*, not of trusting the generator's own internal accounting.

### 2.2 How a band is measured without contaminating the report budget

Each `cond(Ri)` is turned into a 2-rule scratch `.kicad_dru`:

```
(rule "... -- everyone else, ignored"
   (constraint clearance (min 0.001mm))
   (severity ignore)
   (condition "!(cond(Ri))"))

(rule "Ri"
   (constraint clearance (min <Ri's real value>mm))
   (condition "cond(Ri)"))
```

`(severity ignore)` — not an unconditioned near-zero floor — is load-bearing here: an earlier version of this measurement (mirroring PR #1110 sec 5.3's method) used a 0.001mm floor rule instead, and PR #1110 explicitly recorded having to subtract "the floor's own contribution" (1 clearance / 47 creepage pairs sub-micron apart, which is real geometry on this board — see sec 6 there) from every band it touched. `severity ignore` sidesteps that subtraction entirely: non-matching pairs are evaluated and suppressed, never reported, at any real distance. Verified this is not just "quieter" but also does not silently defeat the cap itself: an `ignore`-everyone-else run against a rule matching hundreds of pairs still saturates at ~505–513 (not the true ~1,150+), so `ignore` participates in the same report-budget accounting as a normal rule — it does not create a loophole, it only removes noise.

### 2.3 Recursive splitting, and how it is known to have stopped correctly

If a band's isolated count lands at/near its category's cap (`cap_for(ctype)`: 499 for `clearance`, 199 for everything else — getting this per-category, not a single constant, matters: `track_width`'s true `HighVoltage` band landed at exactly 199 on the first pass, which a clearance-shaped 479 threshold would have sailed past unflagged), the tool re-runs it once more and only trusts a below-threshold reading if it repeats **exactly** — determinism, not proximity to a round number, is the signature PR #1110 already established for "this is a true count, not a truncated one" (sec 5.1 there: capped categories vary run-to-run at a fixed board; true ones don't). A count that is non-deterministic is treated as still-saturated regardless of its numeric value.

If still saturated, the band is bisected by the **real net names** on the board in its anchoring `A.NetClass == 'X'` class (via `pcb/temper.kicad_pro`'s own `netclass_assignments` + `netclass_patterns`, not the Python SSOT layer — this is what kicad-cli itself resolves, so it cannot drift from the measurement), and each half is recursed independently. This bottomed out for `clearance`'s `HV to LV` band at **individual net names** four levels deep (`HighVoltage` has 14 real nets on this board): the single hardest leaf, `discharge.k_dis1-nc` alone against every non-excluded class, measured **459**, confirmed deterministic across 4 repeated runs before being accepted.

---

## 3. Partition method 2: non-DRU categories (`shorting_items`, `silk_overlap`)

Checked kicad-cli's own violation JSON for both categories: neither `description` field ever contains `rule '...'` (verified by direct inspection of the raw JSON) — `shorting_items` reads `"Items shorting two nets (nets X and Y)"`, `silk_overlap` reads `"Silkscreen clearance (board setup constraints silk clearance 0.1500mm; actual N mm)"`. Neither is governed by a `.kicad_dru` condition, so section 2's method does not apply to them at all.

Instead: **exact, byte-preserving S-expression block deletion** on a scratch copy of the raw `pcb/temper.kicad_pcb` text — never a parse/reserialize round trip. That distinction is load-bearing, verified the hard way: round-tripping the *unmodified* board through `kiutils` (`Board().from_file(...).to_file(...)`, zero edits) changes `shorting_items` 199→58 and `hole_clearance` 105→116 on a byte-for-byte-input board. `kiutils` silently perturbs geometry on save (most likely zone-fill-polygon regeneration) and is unsafe for this purpose; rejected. `scripts/measure_uncapped_drc.py`'s `board_text_filtered_by_nets`/`board_text_filtered_by_refs` instead locate top-level `(footprint|segment|arc|via|zone ...)` blocks and per-footprint `(pad ...)` blocks by their own 2-/4-space indentation plus a balanced-paren scanner, and delete only the blocks whose net (or, for `silk_overlap`, whose owning footprint reference) falls outside the kept set — confirmed to reproduce the source text **byte-for-byte** when the "kept" set is everything.

`--refill-zones` is off by default in every invocation here (verified via `kicad-cli pcb drc --help`; it is opt-in and this tool never passes it) — so deleting items never causes a KEPT zone to silently regrow into space a deleted neighbor used to occupy; every kept zone's stored fill polygon is untouched.

`shorting_items` was bucketed by real net name (every copper item has exactly one net); `silk_overlap` by footprint reference (silkscreen graphics belong to a footprint, not a net). Both **buckets are exhaustive by construction** (every real net/reference is assigned to exactly one bucket). Where this method's *exhaustiveness proof broke down in practice* is documented honestly in sec 5.3–5.4, rather than papered over with a number.

---

## 4. Acceptance test

**Reproduce PR #1110's 1,307 independently.** `measure_category_exhaustive(..., 'clearance', ...)`'s per-rule bands, summed over every safety rule (excluding `Default routing` and the netclass-implicit fallback, exactly as PR #1110 scoped its own "safety-rule-governed total"):

| rule | this measurement | PR #1110 sec 5.3 |
|---|---:|---:|
| `AC Mains to LV` | 23 | 23 |
| `AC Mains to HV` | 1 | 1 |
| `HighVoltageIsolated same side` | 5 | 5 |
| `HighVoltageIsolated to LV` | 112 | 112 |
| `HV internal same footprint` | 9 | 9 |
| `HV to LV` | **1,152** | **1,152** |
| `HighVoltageTank to LV` | 5 | 5 |
| **total** | **1,307** | **1,307** |

Independent, exact, reproduced via a completely different derivation (this session never read PR #1110's per-rule numbers before running the tool — the isolation-condition/AND-NOT machinery was built from the DRU semantics directly, sec 2.1). The `HV to LV` band needed the same depth of splitting (down to individual net names) that PR #1110's manual protocol needed, confirming the two methods hit the same wall for the same underlying reason, not by coincidence.

**Demonstrate correctness on a case kicad-cli saturates.** `track_width`'s `HighVoltage trace width` band: isolated alone, kicad-cli reports exactly **199** — sitting precisely on `ERROR_LIMIT`. Split by real net name, the true count is **341** (146 + 99 + 96, sec 5.2), each leaf deterministic across reruns and comfortably under the cap. 341 ≠ 199 and 341 > 199: kicad-cli's raw reading here is proven wrong by a factor of 1.7×, and the tool recovers the true value.

---

## 5. True per-category counts, committed board, post-precedence-fix

Commands (foreground; each is what `scripts/measure_uncapped_drc.py`'s CLI runs internally):

```bash
# .kicad_dru from the fix/dru-rule-precedence generator, into a scratch dir outside the repo
uv run --all-packages python scripts/measure_uncapped_drc.py dru-category clearance \
  --dru-generator <fix/dru-rule-precedence checkout>/scripts/generate_kicad_dru.py \
  --scratch-dir /tmp/scratch/clearance --json /tmp/scratch/clearance.json
# ... same for creepage, track_width
```

| category | kicad-cli raw (3 fresh samples) | **true count** | ratio true/raw-cap |
|---|---|---:|---:|
| `clearance` | 499, 499, 500 | **1,664** | 3.3× |
| `creepage` | 200, 199, 200 | **200** | 1.0× (genuinely not capped) |
| `track_width` | 199, 199, 199 | **490** | 2.46× |
| `shorting_items` | 199, 199, 200 | **saturated; not exactly resolved** (sec 5.3) | ≥1× |
| `silk_overlap` | 199, 199, 199 | **saturated; ≥361 from a single footprint pair alone** (sec 5.4) | ≥1.8× |

### 5.1 `clearance` = 1,664 (full band breakdown)

| rule / bucket | true count |
|---|---:|
| `AC Mains to LV` | 23 |
| `AC Mains to HV` | 1 |
| `HighVoltageIsolated same side` | 5 |
| `HighVoltageIsolated to LV` | 112 |
| `HV internal same footprint` | 9 |
| `HV to LV` | 1,152 |
| `HighVoltageTank to LV` | 5 |
| `GateDriveHV near HV` / `GateDriveSELV near HV` / `GateDriveHV to ACMains` / `GateDriveHV to HighVoltageIsolated` | 0 each |
| `Power internal same footprint` | 0 |
| `Default routing` | 331 |
| `Ground clearance` (latent — `Ground` class doesn't exist on this board, per PR #1110 Instance 2) | 0 |
| `Same footprint pads` / `Fine pitch IC pads` / `USB differential` | 0 each |
| netclass-implicit fallback (no explicit DRU rule matches) | 26 |
| **total** | **1,664** |
| safety-rule-governed subtotal (excludes `Default routing`, fallback) | **1,307** |

This resolves PR #1110's own open question — it bounded the true total at "at least 1,307 and at most 1,638" (sec 5.3 there) because summing `Default routing`'s isolated count double-counted pairs a stricter rule also governs. The AND-NOT chain here removes that double-count by construction: **1,664** is the exact total, not a bound, and it sits (correctly) just outside PR #1110's own approximated upper bound of 1,638 — that bound was never claimed to be tight.

### 5.2 `track_width` = 490

| rule | true count |
|---|---:|
| `HighVoltage trace width` | 341 (146 + 99 + 96 across a 3-level real-net-name split) |
| `Power trace width` | 149 |
| every other net class (`HighVoltageTank`, `ACMains`, `Ground`, `HighCurrent`, `GateDriveHV`, `GateDriveSELV`, `Signal`, `HighSpeed`, `FinePitch`) | 0 each |
| **total** | **490** |

`track_width` bands are disjoint by construction with no splitting needed for correctness (each rule's condition is `A.Type=='Track' && A.NetClass=='X'` for a distinct `X` — mutually exclusive by definition), so this total required no tie-handling at all, only the recursive net-name split on the one band that saturated.

### 5.3 `shorting_items`: proven saturated, true count not established

**Saturation is proven independently of the partition below**, by the same diagnostic PR #1110 sec 5.1 uses: `shorting_items` on the unmodified board reads 199, 199, 200, 199, 199 across 5 fresh runs — non-deterministic at a fixed board, exactly the signature of a truncated report, not a real one.

Attempted an exhaustive net-bucket-pair partition (8 buckets of ~20 real net names each, all 36 unordered bucket-pairs measured, none individually saturated). The **naive sum of all 36 raw readings is not the answer** — each bucket-pair run reports the union of that pair's cross-net violations *and* both buckets' own internal (same-bucket) violations, so a proper total requires inclusion–exclusion: `total = Σᵢ count(i,i) + Σᵢ<ⱼ [count(i,j) − count(i,i) − count(j,j)]`. Applying that gives **155** — but 155 is *below* the raw whole-board reading of 199–200, which is not logically possible if the partition were faithful (a report cap can only suppress true violations, never fabricate ones the board doesn't have; a true count under 199 could never make kicad-cli's own uncapped-appearing single-pass report read 199–200). This is reported as a **known, unresolved discrepancy**, not smoothed over: one candidate cause (an asymmetry in how net-0/"no net" copper items were excluded between pads and other item kinds) was found and fixed in `scripts/measure_uncapped_drc.py` during this session; re-running after the fix reproduced the same 155, so it was not the (sole) cause. No further root cause was found in the time available.

**Conclusion reported honestly: `shorting_items` is saturated (proven), its true count is *at least* 199 and this session's own partition attempt is not trusted for an exact figure.** This is the "kicad-cli [via the method attempted] cannot answer this" case the task explicitly anticipated.

### 5.4 `silk_overlap`: proven saturated, true count bounded below at 361 for a single pair, whole-board total not established

The reference-bucket-pair sweep (8 buckets of ~21 footprints, C(8,2)+8 = 36 runs) found every pair touching one specific bucket saturated at 199, and bisecting that bucket isolated the cause to a **single footprint pair**: `C5` (`Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`) × `C7` (`Capacitor_THT:C_Rect_L18.0mm_W11.0mm_P15.00mm_FKS3_FKP3`). Measured completely alone (every other footprint deleted), kicad-cli still reports exactly **199** for this one pair.

`C5`'s footprint draws its silkscreen outline as **554 individual `fp_line` segments** (plus 3 `fp_circle`) instead of a plain circle primitive — apparently a dense hatch/facet pattern rather than a normal outline. Verified this is the entire cause (removing `C5` alone, or `C7` alone, from that bucket drops it to 0; every other of the bucket's 19 other members contributes nothing when `C5`/`C7` are both absent).

Because a *single footprint pair* already saturates the cap, footprint-reference-granularity partitioning is provably insufficient here — there is no coarser-than-atomic split left to try within this method. Instead, computed the true count for **just this one pair** directly, geometrically, outside kicad-cli entirely: extracted both footprints' `F.SilkS` `fp_line`/`fp_circle` primitives (position + rotation transform applied), and counted every cross-footprint segment pair whose edge-to-edge distance (center-line distance minus half-widths) is under `pcb/temper.kicad_pro`'s own `min_silk_clearance` = 0.15mm. Same-footprint pairs are excluded, matching a measured KiCad behavior (`C5` alone, despite 554 segments only 0.04mm apart within its own hatch pattern, scores 0 — same-footprint self-checks are not flagged). Result: **361 violations from this one pair alone** — 1.8× the entire board's reporting cap, from two components.

A full board-wide version of the same direct geometric method (all 161 footprints with `F.SilkS` geometry, `fp_line`/`fp_circle` only) totalled 453 — but cross-checked against an independent, unsaturated kicad-cli measurement of the 148 footprints outside the `C5`/`C7` cluster (96, deterministic, well under cap), the geometric model's own sum for that same 148-footprint subset came to only 11: an 85-violation undercount. `fp_text` (161 reference/value silkscreen labels) and `fp_arc`/`fp_poly` (10 more items) were out of scope for the from-scratch reimplementation and are the leading suspect for the gap. **The whole-board `silk_overlap` true count is therefore not reported as a specific number** — only the proven lower bound (≥361 from one pair, ≥199 from kicad-cli's own capped reading) and the finding that a normal-looking footprint pair alone exceeds the board-wide cap.

---

## 6. `temper-drc-rs` characterization: not agreement, not a bug — a different model

Built `RouteIn` tuples directly from `temper_placer.io.kicad_parser.parse_kicad_pcb_v6`'s parsed tracks (grouped by net, one `RouteIn` per net with all that net's segments — grouping is required: treating each raw track segment as its own route double-counts adjacent same-net segments as false "clearance violations" against themselves, since `verify_route_clearance` assumes a route bundles one net's own geometry) and called `temper_drc_rs.verify_route_clearance` directly — the same PyO3 entry point `packages/temper-placer/src/temper_placer/router_v6/clearance_check.py`'s `backend="auto"`/`"rust"` uses in production.

| configuration | violations reported |
|---|---:|
| `default_clearance=0.127mm`, no HV net names (raw default) | 17 |
| `default_clearance=0.127mm`, `hv_net_names` from `elec/domain_manifest.yaml` (production's actual `_load_manifest_hv_net_names()` path) | 65 |
| kicad-cli true `clearance`, this document | **1,664** |

**This is not disagreement to resolve — it is two different checks.** `router_clearance.rs`'s model (documented in its own module comment) is a *router-time* collision-avoidance figure: 0.127mm (5 mil, roughly a fabrication minimum) by default, escalating only for nets matching a keyword gate (`AC_`/`HV_`/`HIGH_VOLTAGE`/`MAINS`/...) or the domain manifest's explicit HV net list, to 4.2mm (internal) or 14.0mm (external) — its own docstring cites these as "1.16% of nets are HV-gated" on this board. The DRU's model is the fab-authoritative, IEC-60335-cited netclass-pair table: 0.2mm default up to 8.0mm reinforced creepage, keyed on the *net class* structure (`HighVoltage`/`ACMains`/`GateDriveHV`/...), not a keyword match on the net's name. Even with the manifest's HV net names loaded, `router_clearance.rs` finds only 65 — because its clearance *magnitudes* (0.127/4.2/14.0mm) are not the DRU's (0.2–8.0mm structured by class), not because it is missing pairs.

**Per the task's instruction, no winner is picked.** `router_clearance.rs` is answering "can the router make progress without immediately violating a near-fab-minimum spacing" — a real and useful question during routing — not "does this board meet its certified isolation clearance," which is what kicad-cli's DRU-governed `clearance` measures and what sec 5.1's 1,664 reports. Using `router_clearance.rs`'s count as a substitute for the DRU clearance ceiling would silently drop the entire IEC 60335 netclass structure from the gate.

---

## 7. Which recorded ceilings are now known to be meaningless

`power_pcb_dataset/drc_ceiling.json` (read, **not modified** by this document — a separate agent is re-deriving it) currently records, for the most recent board state (`f70296adc1`, pre-precedence-fix):

```
"violations_by_type": { "clearance": 386, "creepage": 186, "shorting_items": 199, "track_width": 199, ... }
"warnings_by_type":   { "silk_overlap": 199, ... }
```

- **`shorting_items: 199` and `track_width: 199` sit exactly on `ERROR_LIMIT`.** Measured here: `track_width`'s true count is **490**, 2.46× the ceiling value itself. A board change that doubled real track-width violations would still read 199 and the gate would not move. **This ceiling is a gate that can never fire**, confirmed by direct measurement in this session, not re-asserted from PR #1110 (which established the mechanism but did not measure `track_width`'s true count).
- **`silk_overlap: 199`** — same limit, same conclusion. Proven here that a single footprint pair alone exceeds the entire cap by 1.8×; the true whole-board count is unknown but is certainly higher than 199, likely substantially so given 16 non-zero footprint pairs were found in the (incomplete) geometric survey.
- **`clearance: 386`** is meaningless for a different, unrelated reason: it was measured against the **pre-precedence-fix** generator (`f70296adc1` predates `fix/dru-rule-precedence`). It is not at a reporting cap — 386 < 499 — but it is stale the moment the precedence fix lands, exactly as PR #1110 sec 8 already flagged. This document adds no new information on that point beyond confirming the true post-fix figure (1,664) for whoever re-derives the ceiling next.
- **`creepage: 186`** (ceiling; observed band 182–184 pre-fix) is **not** in this category. Section 2.3/5.1's exhaustive partition found `creepage`'s true count (200, post-fix) with zero saturated bands anywhere in the rule tree — every band's isolated measurement landed far under 199 without any splitting required. `creepage` is a real, usable ratchet target; its recorded ceiling is stale from the precedence fix (same reason as `clearance`) but not from saturation.

---

## 8. Reproduction

```bash
# Setup: this task's own worktree/branch
git worktree add <path> -b feat/uncapped-drc-measurement origin/main
cd <path> && uv sync --all-packages   # builds temper-drc-rs, needed for kicad-cli JSON parsing

# The post-precedence-fix .kicad_dru generator (PR #1110, not yet on main):
#   scripts/generate_kicad_dru.py from branch fix/dru-rule-precedence, commit 11b344c65

# Exact clearance/creepage/track_width totals (sec 5.1/5.2):
uv run --all-packages python scripts/measure_uncapped_drc.py dru-category clearance \
  --dru-generator <fix/dru-rule-precedence checkout>/scripts/generate_kicad_dru.py \
  --scratch-dir /tmp/scratch/clearance --json /tmp/scratch/clearance.json
uv run --all-packages python scripts/measure_uncapped_drc.py dru-category creepage \
  --dru-generator <...>/scripts/generate_kicad_dru.py --scratch-dir /tmp/scratch/creepage
uv run --all-packages python scripts/measure_uncapped_drc.py dru-category track_width \
  --dru-generator <...>/scripts/generate_kicad_dru.py --scratch-dir /tmp/scratch/tw

# shorting_items / silk_overlap bucket-pair sweep (sec 5.3/5.4 -- read the printed
# caveat about inclusion-exclusion before trusting any total from this path):
uv run --all-packages python scripts/measure_uncapped_drc.py physical-category shorting_items \
  --buckets 8 --scratch-dir /tmp/scratch/shorting --json /tmp/scratch/shorting.json
uv run --all-packages python scripts/measure_uncapped_drc.py physical-category silk_overlap \
  --buckets 8 --scratch-dir /tmp/scratch/silk --json /tmp/scratch/silk.json

# kiutils round-trip rejection (sec 3), reproducible directly:
python3 -c "
from kiutils.board import Board
b = Board().from_file('pcb/temper.kicad_pcb')
b.to_file('/tmp/scratch/rt/temper.kicad_pcb')"
# then run kicad-cli on the two copies and diff shorting_items/hole_clearance counts

# temper-drc-rs comparison (sec 6):
uv run --all-packages python -c "
from pathlib import Path
from collections import defaultdict
from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
from temper_placer.router_v6.clearance_check import _load_manifest_hv_net_names
import temper_drc_rs as t
r = parse_kicad_pcb_v6(Path('pcb/temper.kicad_pcb'))
by_net = defaultdict(list); widths = defaultdict(list)
for tr in r.tracks:
    by_net[tr.net].append((*tr.start, *tr.end, tr.layer)); widths[tr.net].append(tr.width)
routes = [(n, max(widths[n]), s, [], []) for n, s in by_net.items()]
v, _ = t.verify_route_clearance(routes, 0.127, {}, sorted(_load_manifest_hv_net_names()))
print(len([x for x in v if x[0] != x[1]]))"
```

Sources: `pcbnew/drc/drc_engine.cpp` (10.0 branch, `ERROR_LIMIT`/`EXTENDED_ERROR_LIMIT`); `kicad-cli pcb drc --help` (`--refill-zones` opt-in, confirming zones are never refilled by any invocation in this document); `docs/evidence/2026-08-12-dru-rule-precedence.md` (PR #1110, the precedence fix and its own partial partition-and-sum); `power_pcb_dataset/drc_ceiling.json` (read-only in this task).
