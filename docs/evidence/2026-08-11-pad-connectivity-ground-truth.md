<!-- provenance: commit=528afb18b0c0e4fc09ff6980298ef9d4d06ba474 dirty=false (HEAD at measurement time, branch docs/pad-connectivity-ground-truth). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, identical to the hash recorded in docs/evidence/2026-08-11-true-pad-connectivity-baseline.md and docs/evidence/2026-08-11-stage4-placement-congestion-spike.md -- same board, unchanged since 2026-08-08, no re-route performed. Board and generated .kicad_dru staged to a scratch copy for kicad-cli, never written back; pcb/temper.kicad_pcb itself was never touched. kicad-cli version 10.0.5 (confirmed via `kicad-cli version` and the DRC report's own `kicad_version` field). -->

# Pad-connectivity ground truth: reconciling four completion numbers against KiCad's own DRC

**Date:** 2026-08-11

## Headline

**0 of the board's 110 real electrical nets (0.0%) are verifiably routed, using
110 official schematic nets and 487 physical pads as the denominator —
and this is not a re-measurement that changes the story, it is
independent confirmation from a fourth, previously-unconsulted oracle.**
KiCad's own DRC engine (`kicad-cli pcb drc`, 10.0.5) reports at least one
missing connection for **all 110 of 110** official nets — zero exceptions,
in both the board's as-committed zone-fill state and after a forced
`--refill-zones` recompute. **0/110 was correct all along.** The
`pad_connectivity_audit.py` figure this repo already uses agrees with
KiCad exactly, not by chance (see §4's controls), and every other number in
circulation is real but answers a different, weaker question than
"is this net done."

## 1. Method

Ran `kicad-cli pcb drc` (10.0.5) against a **scratch copy** of
`pcb/temper.kicad_pcb` — the committed file itself was never written to.
The board was staged with `temper.kicad_pro` beside it (same stem) and a
freshly generated `temper.kicad_dru` (`.venv/bin/python
scripts/generate_kicad_dru.py`, not committed, per its own gitignore
entry). Environment:

```
LD_LIBRARY_PATH=<every dir under kicad-10.0.5/root containing a .so>
KICAD_STOCK_DATA_HOME=<prefix>/root/usr/share/kicad
kicad-cli pcb drc --format json --severity-all --exit-code-violations -o drc.json temper.kicad_pcb
```

Confirmed the project actually resolved (not silently dropping custom-rule
violations, per this task's own warning): the output JSON's `kicad_version`
field reads `10.0.5`, and it contains 184–186 `creepage` violations — a
constraint type that exists *only* in the generated `.kicad_dru`, so its
presence proves the `.kicad_pro`/`.kicad_dru` pair was found and parsed.
`ignored_checks` in the report names four checks unrelated to connectivity
(`track_not_centered_on_via`, `tuning_profile_track_geometries`,
`footprint_filters_mismatch`, `footprint_type_mismatch`) — `unconnected_items`
is not among them, so the numbers below are the full, unsuppressed
connectivity check.

Ran DRC twice: once against the board's zone fill as committed
("nofill"), once with `--refill-zones` ("refill") — see §6 for why both
were run and whether it matters.

**110-official-net list** was pulled independently via
`temper_placer.io.kicad_parser.parse_kicad_pcb(...).netlist.nets` — the
same call the prior `pad_connectivity_audit` baseline doc used — giving
110 names, matching every prior evidence doc's denominator.

## 2. KiCad's own connectivity verdict — the ground truth

`unconnected_items` entries each pair two "items" (a pad, a bare dangling
track segment, or a bare via) with the description "Missing connection
between items." Parsed all of them (regex on each item's `description`
field, validated against the raw file by UUID lookup — see §5):

| Fill state | `unconnected_items` entries | Official nets with ≥1 missing connection | Official nets **fully connected** | Distinct pad-tuples cited |
|---|---:|---:|---:|---:|
| As-committed ("nofill") | 428 | **110 / 110** | **0 / 110** | 483 |
| `--refill-zones` ("refill") | 427 | **110 / 110** | **0 / 110** | 478 |

**Every single one of the 110 official nets has at least one entry in
KiCad's own unconnected-items report, in both fill states.** That is
KiCad's own reckoning of "how much of this board is routed": **0/110,
0.0%.** This is the ground truth the rest of this document reconciles
everything else against.

(Full violation counts, for context only — not a completion metric:
1534 violations nofill, 1825 refill. The `--refill-zones` state visibly
exposes more `creepage`/`clearance` violations once pours are actually
filled; see §6.)

## 3. The reconciliation table

| Source | Number | What it actually measures | Agrees with KiCad? |
|---|---:|---|---|
| **KiCad DRC** (`kicad-cli pcb drc`) | **0/110 nets fully connected**; 428 missing-connection entries | Ground truth: every pad of a net actually joined by real copper, KiCad's own connectivity engine | — (this is the reference) |
| `nets_carrying_copper()` | 64/110 (58.2%) | Nets with *any* copper (explicit trace/via **or** zone pour) bearing the right net number, anywhere on the board | Not comparable directly — answers "started," not "finished." Every one of the 64 is still in KiCad's 110-broken set. |
| `pad_connectivity_audit.audit_pcb_file`, 110-net denominator | **0/110 (0.0%)** | Every pad of a net in one copper-connected component | **Exact match.** Confirmed non-coincidental — see §4. |
| Same tool, unfiltered 139-net denominator | 29/139 (20.9%) "fully connected" | Same check, but the 139 includes 29 board-only single-pad artifacts outside the schematic netlist | Consistent, not contradictory — see §3a. Wrong denominator for a completion percentage (§7). |

### 3a. The 29/139 figure is not a disagreement, it's a different (wrong) denominator

The 139-net set (`audit_pcb_file`'s own key set) is every net name with at
least one footprint pin, including 29 names absent from the schematic
netlist — unpopulated MCU GPIOs, NC pads, floating USB/RTD test pins.
Every one of the 29 has exactly 1 pad; a net with ≤1 pad is trivially
"fully connected" by the tool's own stated rule (`len(pads) <= 1` returns
`fully_connected=True` immediately, `pad_connectivity_audit.py:169-176` —
nothing to join). **KiCad agrees, independently:** none of the 29
non-official names appears anywhere in KiCad's own `unconnected_items`
report (checked directly — `nets_with_issue - official = {}` in both fill
states). KiCad never flags a 1-pad net either, for the identical reason.
29/29 cross-validate between the two tools on triviality; the 29 are just
not a completion signal for anything (§7).

## 4. Verifying the tool, not just trusting its agreement

A tool that lands on 0/110 could be broken in a way that always says "no."
Two controls, run directly against
`temper_placer.router_v6.pad_connectivity_audit.check_net_pad_connectivity`
— the exact core function `audit_pcb_file` calls per net, no
reimplementation:

**Positive control (synthetic, but the real production function):** two
pads at `(0,0)` and `(5,0)` joined by one segment running exactly pad to
pad. Result: `fully_connected=True`, `pads_connected=2/2`. ✓ correctly
recognizes a genuinely complete net.

**Negative control 1 (synthetic):** same two pads, segment stops 2mm short
of pad 2 (a dangling stub — the exact `fallback_channel_path` shape
documented in the prior baseline doc). Result: `fully_connected=False`,
`is_fake_completion=True`. ✓ correctly rejects a stub that doesn't reach.

**Negative control 2, real board, hand-traced:** net `DISCHARGE_CTRL`
(2 pads: `R17.1` at `(38.2325, 36.16)`, `U27.24` at `(26.48, 38.96)`).
The tool reports `fully_connected=False`, `pads_connected=1/2`, both pads
unreached. Manually pulled every `(segment ...)` block on this net's
number (24 segments) directly from the raw file: they form one continuous
trace confined to `x∈[164.45, 169.05], y∈[31.83, 139.1]` — nowhere near
either pad (`x∈[26–38], y∈[36–39]`). Real copper exists on this net; it
provably never reaches its own pads. **KiCad's independent DRC names the
exact same two pads** (`Pad 1 [DISCHARGE_CTRL] of R17`, `Pad 24
[DISCHARGE_CTRL] of U27`) as unconnected. Two independently-implemented
connectivity engines, reasoning over the same raw geometry, reach the same
verdict for the same reason — not an accidental agreement on a net-level
yes/no.

The tool's own suite (`test_pad_connectivity_audit.py`, 10 tests) also
passes cleanly on this checkout (`.venv/bin/python -m pytest
packages/temper-placer/tests/router_v6/test_pad_connectivity_audit.py -q`
→ 10 passed). Note: this checkout's shared `.venv` initially had 7 stale
pyo3 extensions (built 2026-08-09, source since changed) that broke even
`import temper_placer`; resolved with `make venv-isolate` in this worktree
before any measurement below — see the provenance note. This is a
pre-existing environment-hygiene issue unrelated to the audit tool itself.

## 5. Resolving the zone blind spot

`pad_connectivity_audit.py`'s `_parse_segments_and_vias` has no code path
for `(zone ...)` blocks (confirmed by reading the module — only
`segment`/`via` extraction) — a documented, real gap. 13 official nets are
zone-pour-only (no explicit trace/via): `+15V`, `+15V_LS`, `+3V3`,
`DC_BUS_RTN`, `GATE_HS`, `PWM_HS`, `PWM_LS`, `PWR_RTN`, `SW_NODE`,
`V_BUS_SENSE`, `ac_l`, `ac_n`, `vcc`. The audit tool cannot distinguish
"pour reaches every pad" from "not connected" for these 13 — it reports
`has_any_copper=False` for all of them, the same as a genuinely unrouted
net.

KiCad *does* read zone geometry, so it resolves the ambiguity directly:

| | nofill | refill |
|---|---:|---:|
| Of the 13 zone-only nets, how many does KiCad still flag as broken | **13 / 13** | **13 / 13** |
| Nets where refill measurably reduces the missing-pad count | — | `DC_BUS_RTN` (11→9), `SW_NODE` (7→4) |
| Nets flipped to fully connected by resolving the blind spot | **0** | **0** |

**All 13 remain not-fully-connected under KiCad, in both fill states.**
Two of the 13 (`DC_BUS_RTN`, `SW_NODE`) do show the pour genuinely joining
a few additional pads once properly filled — proof the blind spot is real,
the audit tool really is missing information those two nets have — but it
never flips a net to complete. **The 0/110 headline is not inflated by the
zone blind spot; it is independently confirmed by the one tool that can
see zones.** Quantifying the ask directly: of the 0/110 figure, 110/110
(100%) is now real and KiCad-verified; 0/110 is unverifiable-by-the-audit-
tool-alone, because KiCad closes every one of those 13 cases itself.

## 6. Does zone fill state change the answer?

`--refill-zones` recomputes pour geometry from current pad
positions/rules instead of trusting whatever was last saved. It changes
the **violation total** noticeably (1534→1825, mostly `creepage`/
`clearance` now visible against completed pours) and trims the
unconnected-item count slightly (428→427 entries; 483→478 cited pads;
§5's two-net improvement). **It does not change the net-level answer**:
110/110 broken, 0/110 complete, in both states. **Refill is the more
honest baseline** going forward — it reflects the rules and pad positions
as they stand today rather than a fill that may be stale relative to the
last save — but for this document's headline, the choice is immaterial.

## 7. The denominator question, settled

**Adopt 110 nets / 487 physical pads.** Reject 139 nets / 493 or 522
pin-instances.

- **110 vs 139 nets:** the extra 29 are not electrical nets a fabricated
  board needs to route — they are unpopulated pins, NC pads, and floating
  test points with exactly one physical terminal each. A single-pad net
  has no connection to make; counting it as "fully connected" doesn't
  reflect any routing work done, it just reflects that there was nothing
  to do. KiCad's own DRC treats them identically (never flags them, for
  the same reason) — this isn't a case of a stricter tool disagreeing, the
  29 simply don't belong in a "how much is routed" metric at all.
- **493 vs 487 pads (110-net denominator):** `pad_count` as reported by
  `NetConnectivityResult` is a **schematic pin-instance** count, not a
  physical-pad count. Six nets (`PWR_RTN`, `DC_BUS_RTN`,
  `discharge.k_dis1-nc`, `discharge.k_dis1-no`, `discharge.k_dis2-nc`,
  `discharge.k_dis2-no`) each have one physical relay pad
  (`K2.1`/`K3.1`/`K2.4`/`K2.3`/`K3.4`/`K3.3`) referenced by **two**
  schematic pin numbers (a relay coil/contact symbol convention), so it is
  counted twice. `493 - 6 = 487` distinct physical `(reference, pad
  number)` pairs — confirmed by independently re-deriving the pad list via
  `_pads_by_net` and diffing. Fabrication cares about physical copper
  joints, not schematic pin multiplicity, so **487 is the correct pad
  denominator.**
- **522 (139-net pad total) is the 493 pin-instance count plus the 29
  single-pad extras**, `493 + 29 = 522` exactly (no duplicate-pin issue
  among those 29) — same reasoning as the net-count question applies.

**Convention this repo should use from now on: report completion as
`X/110 nets`, and where a pad-level figure is needed, `Y/487 pads`.**
Retire 139/493/522 to a footnote explaining how the raw parse gets there,
not a headline number.

### 7a. Reconciling KiCad's own pad count (483/478) against 487

KiCad's distinct-pad-tuple counts (483 nofill, 478 refill) are **not**
directly comparable to 487 as a "how many pads does this board have"
figure — they are a **lower bound**, because `unconnected_items` reports
the *minimum* set of ratsnest edges needed to signal what's still missing,
not an exhaustive per-pad listing. When several pads of one broken net are
already joined to each other (or to a dangling stray trace/via) by real
copper, KiCad can cite one representative node for that sub-island instead
of every pad in it. Traced all 4 pads present in the 487-pad set but
absent from KiCad's nofill citation list:

- `K1.13`, `K1.14`, `K2.2` — each sits on a net with real (if incomplete)
  copper; KiCad's report instead names a dangling free end of that same
  net's own trace as the "other" unconnected item, which is the
  representative-node effect described above.
- `R71.2` (net `gnd`) — a distinct, smaller finding: `R71.2` sits at
  `(116.535, 144.9)`, within 0.05mm of a `clearance` violation KiCad
  reports at `(116.55, 144.95)` against a segment nominally on net 60
  (`hb.gate_hs.driver-p2`). The two appear to be physically touching — a
  candidate real short between `gnd` and an HV-adjacent gate-drive net.
  KiCad's connectivity engine merges physically-touching copper into one
  island before generating its report, so `R71.2` never needs its own
  citation; the island's other member (the net-60 track) stands in for it.
  **This is a genuine finding surfaced while reconciling a pad count, not
  a routing-completion question** — flagging it here for whoever owns
  clearance/short remediation; no fix attempted, per this task's
  boundaries.

This same physical-touch mechanism explains a broader labeling quirk
worth recording: of the 100 non-pad (`Track [...]`/`Via [...]`) endpoints
across the 428 nofill entries, 16 name a net in their description that
does **not** match the object's own `(net N)` attribute in the raw file
(verified by UUID lookup against every one). All 16 pair with a pad from a
*different*, real net at a position matching a reported `clearance`
violation — i.e., real copper of one net touching real copper of another.
This is either a kicad-cli 10.0.5 JSON-report labeling quirk (using the
edge's "expected" net rather than the object's stored net) or a small
cluster of undocumented shorts; either way it **never changes which net
has a missing connection** (verified: it only ever affects the label of
the second, non-pad item in a pair whose pad-side item is independently
confirmed correct against the raw file in every sampled case), so it does
not alter any conclusion in this document. Worth its own focused
investigation, out of scope here.

## 8. `gnd`: 86, not 87

**86 is correct**, confirmed two independent ways:

1. `pad_connectivity_audit.audit_pcb_file(...)["gnd"].pad_count == 86`
   (schematic-pin-derived, via `pin_world_position`/`component.pins`).
2. Direct count of pad-context occurrences of `(net 50 "gnd")` in the raw
   file (`grep -c '(net 50 "gnd"))'`, requiring the pad-closing paren) = 86.

**87 is a naive string-count artifact.** `grep -c '(net 50 "gnd")'`
(without requiring the trailing pad-closing paren) returns 87 because it
*also* matches the net's own one-time top-level table declaration,
`(net 50 "gnd")` at line 86 of the file — that line names the net, it is
not a pad. Counting it as a pad is an off-by-one from not distinguishing
"a pad references this net" from "this net exists." **Use 86 going
forward; 87 should not be quoted again.**

Independent of the pad-count question: `gnd` has confirmed **zero**
segment, via, or zone copper anywhere in the file (`_extract_top_level_blocks`
over all three block types, filtered to net 50, returns 0 matches for
each) — the board's single largest net, more pads than the next five
largest combined, has no ground copper of any kind. KiCad's report (85 of
86 pads cited directly, the 86th explained in §7a) independently confirms
`gnd` is catastrophically disconnected — 0 of 86 pads reach any other pad
via `gnd`'s own copper, regardless of which pad-count figure is used.

## 9. Full per-net bucket, reproduced fresh

Reproducing the prior baseline doc's bucketing directly against this same
board, this run:

| Bucket | Count | Definition |
|---|---:|---|
| Fully pad-connected (audit tool, matches KiCad exactly) | 0 | every pad in one connected component |
| Fake completion | 51 | explicit segment/via copper exists, but doesn't join all pads |
| Zone-pour-only (audit blind spot; independently confirmed still broken, §5) | 13 | no explicit copper, zone pour exists |
| Zero copper of any kind | 46 | no segment, no via, no zone |
| **Total** | **110** | |

`51 + 13 = 64`, exactly `nets_carrying_copper()`'s figure — confirming
this is the same board measured the same way, with the pad-reachability
check (and now, KiCad's own oracle) added on top.

## 10. Conclusion

**0/110 was correct all along.** Every number this document set out to
reconcile is now accounted for:

- `nets_carrying_copper()` = 64/110: real, but measures "has any copper,"
  not "is done." Every one of the 64 is still broken by KiCad's reckoning.
- `pad_connectivity_audit` 0/110: **exactly matches KiCad**, verified
  non-coincidentally via controls (§4).
- 29/139: not a disagreement, a different (wrong, now-retired) denominator
  for the same trivial single-pad nets (§3a, §7).
- KiCad DRC, 428 unconnected items: the ground truth. 110/110 nets
  broken, 0/110 complete, in both zone-fill states (§2, §6).
- Zone blind spot: real in the audit tool, but resolved by KiCad to be
  worth 0 additional complete nets on this board today (§5).
- `gnd` 86 vs 87: 86 is correct; 87 was a string-count artifact that
  double-counted the net's own declaration line (§8).
- Pad denominators 493/522 vs 487: pin-instance double-counting
  (6 shared relay pads) and 29 non-electrical single-pad extras,
  respectively; 487 is the correct physical-pad denominator (§7).

**Convention adopted, effective this document:** report board routing
completion as **X/110 nets** (and, where a pad-level figure is wanted,
**Y/487 pads**), using KiCad's own DRC (`kicad-cli pcb drc`,
`unconnected_items`) as the authoritative check whenever it is available,
with `pad_connectivity_audit.py` as the fast, KiCad-independent
approximation it has now been shown to agree with exactly on this board.
Today, both read **0/110 — 0.0%**.
