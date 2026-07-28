# Netlist domain-partition check: falsifier, proof it fires, proof it's not vacuous

<!-- provenance: commit=c9be0b1f2421c5adfbe0cbf2681aad8938c8e546 dirty=UNKNOWN -->

**Scope:** `scripts/check_domain_partition.py` (the gate), `elec/domain_manifest.yaml`
(the declared HV/SELV domains and isolator pin-groups), `scripts/tests/test_check_domain_partition.py`
(33 unit tests), `.github/workflows/python-tests.yml` (CI wiring). All
measurements below were taken at commit `ee9b0323181988041e52dfc425c4239c0b6c658d`
and then **re-verified after a further rebase** onto the tip of
`docs/methodology-loop-discipline` (final commit `b713246912b681bcb07b15c6e7b1223b03801902`,
confirmed: `git merge-base --is-ancestor docs/methodology-loop-discipline HEAD`
exits 0) with a freshly rebuilt netlist (`rm -rf elec/build && make netlist`
→ exit 0, 76/76 PASSED, 0 FAILED). Every number and path in §2-§3 is
unchanged between the two commits — re-measured, not assumed carried
forward.

**Falsifier, stated before implementing:** *this check is vacuous if it
reports PASS on the currently committed netlist.* The design's own galvanic
isolation barrier has an open, documented gap (below) at every commit this
check was built and re-verified against; a domain-partition check that does
not find it has failed to check anything real.

**Result: the falsifier did NOT fire.** Measured directly (§2): the gate
exits 3 (VIOLATION) on the current netlist and prints the exact resistor
path from the HV bus to SELV ground.

---

## 0. What this check is answering, and why it had to be rebuilt mid-task

The task brief's original seed defect — `power_return ~ gnd`, a single-point
star join that shorted the AuxSupply's 4.2kVAC isolation barrier outright
(`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` §2) — was fixed on
`docs/methodology-loop-discipline` by a concurrent agent while this task was
in progress (commits `6976ef44`/`1390e807`,
`docs/hardware/SELV_ISOLATION_REDESIGN.md`). Per instruction, this check was
rebased onto that fix (three times, as the branch kept advancing) rather than
built against a stale base, and re-verified against a **freshly built**
netlist (`make netlist`, gitignored `elec/build/`, never committed) at each
rebase.

The redesign's own audit (`SELV_ISOLATION_REDESIGN.md` §4, rows 3–4) already
names the gap that remains: `OVPComparator`'s bus-voltage-sense divider
(`main.ato:434-435`, `safety.dc_bus.line ~ dc_bus_plus` /
`safety.dc_bus.reference ~ gnd`) is a plain resistor chain — no isolator in
the path — bridging the HV half-bus straight into SELV ground. This is now
the check's primary target, and the check finds it as an automated,
positive proof rather than an audit note.

---

## 1. How the manifest and the check model the design

`elec/domain_manifest.yaml` declares two domains by their **exact, literal
compiled net names** (never a pattern or naming convention — the design's own
history includes a net named `+340V_BUS` that was actually a 170V half-bus,
which is exactly the failure mode "infer domain from net name" would walk
into):

- **HV**: `ac_l`, `ac_n`, `+170V_BUS` (renamed from `+340V_BUS` in the SELV
  fix), `DC_BUS_RTN`, `PWR_RTN`, `w1_1`, `w1_2`, `+15V_LS`, `SW_NODE`,
  `GATE_HS`, `GATE_LS`, `zcd`, `a`.
- **SELV**: `gnd`, `+15V`, `+3V3`, `usb_dn`, `usb_dp`, `i2c_sda_ui`,
  `i2c_scl_ui`, the RTD SPI/DRDY/fault/force/sense nets, `WDT_KICK`,
  `WDT_RESET_N`, `SHUTDOWN`, `RELAY_CTRL`, `DISCHARGE_CTRL`, `V_BUS_SENSE`,
  `PWM_HS`, `PWM_LS`, `ZCD_ISO`.

Eight components are declared as isolators, each keyed by **`instance_path`
— the dotted atopile path from the netlist's `sheetpath` field (e.g.
`aux_supply.psu`), never by ref designator or by `libsource`/part name.**
This distinction is load-bearing, confirmed by direct measurement: this
netlist's `libsource` "part" field collapses ten structurally different
parts (all comparator/watchdog/reference ICs sharing a SOT-23-5 footprint)
onto the single string `REF2025AIDDCR`:

```
U9  part=REF2025AIDDCR  sheet=rtd_pan.reference
U15 part=REF2025AIDDCR  sheet=safety.ocp.comp
U16 part=REF2025AIDDCR  sheet=safety.ovp.comp
U17 part=REF2025AIDDCR  sheet=safety.thermal.comp
U18 part=REF2025AIDDCR  sheet=safety.coil_thermal.comp
U19 part=REF2025AIDDCR  sheet=safety.wdt.wdt
```

`sheetpath` stays distinct per instance throughout. Ref designators are
*also* not a safe key across rebuilds: rebasing onto the SELV fix added the
new opto (`U3`), which pushed the gate driver from `U6`→`U7` and the boot
diode from `U7`→`U8` — this check's isolator matching is unaffected because
it never looks at the ref number, only at `instance_path`.

The eight declared isolators: `aux_supply.psu` (IRM-10-15 transformer),
`hb.gate_hs.driver` (UCC21550 gate driver), `ct_sense.ct` (CST3015 current
transformer), `power_in.bypass_relay` / `discharge.k_dis1` / `discharge.k_dis2`
(relay coil vs. contacts), `power_in.zcd_opto` (the new H11L1 optocoupler),
and `power_in.y_cap_pe` — a **stated and defended capacitor policy**: every
ordinary two-terminal part (resistor, inductor, generic capacitor) is
CONDUCTING by default; only `C6`, a certified Y1-class safety capacitor
(IEC 60384-14) whose entire regulatory purpose is a bounded, high-impedance,
DC-blocking AC path across the barrier, gets a declared exception. A generic
bulk/decoupling capacitor bridging domains would remain a violation. This
is the only capacitor in the manifest granted this treatment.

**Mechanism** (`scripts/check_domain_partition.py`): parse the compiled
netlist into a graph of nets; every *undeclared* component conducts across
all of its pins (fail-closed default — the danger is missing a real short,
not over-reporting); every *declared* isolator conducts only within its own
group. Two checks run: (1) no HV-declared net and SELV-declared net share a
connected component; (2) no declared isolator's own groups share a connected
component with each other (its own barrier bridged elsewhere in the
network). Both report the actual net-by-net path, not just "connected."

---

## 2. Proof it FAILS on today's netlist, with the specific path

Measured in the foreground, output captured to a file before reading it
(never through a pipe), at commit `ee9b0323` with a netlist built the same
session (`find elec/src -name "*.ato" -newer elec/build/default.net` returns
nothing — not stale):

```
$ uv run python scripts/check_domain_partition.py > /tmp/EVIDENCE_final_run.txt 2>&1
$ echo "exit=$?" > /tmp/EVIDENCE_final_exit.txt
$ cat /tmp/EVIDENCE_final_exit.txt
exit=3
```

Relevant excerpt:

```
Checked 39 declared nets across 2 domains (HV, SELV), 8 declared isolators, over
160 compiled nets / 167 components.

=== DOMAIN VIOLATIONS: 1 ===

  Domain 'HV' and domain 'SELV' are NOT disjoint (3 independent bridge(s) found):
    [1] '+170V_BUS' --[safety.ovp.r_div_top1 (R51)]--> 'safety.ovp.r_div_top1-p2'
        --[safety.ovp.r_div_top2 (R52)]--> 'safety.ovp.r_div_top2-p2'
        --[safety.ovp.r_div_top3 (R53)]--> 'safety.ovp.comp-inp'
        --[safety.ovp.r_div_bot (R54)]--> 'gnd'
    [2] '+170V_BUS' --[safety.ovp.r_adc_top (R58)]--> 'V_BUS_SENSE'
    [3] 'SW_NODE' --[hb.gate_hs.neg_bias_zener (D5)]--> 'hb.gate_hs.driver-p2'
        --[hb.gate_hs.boot_cap (C17)]--> 'hb.gate_hs.driver-p1-1'
        --[hb.gate_hs.boot_diode (U8)]--> '+15V'

FAILED -- 1 domain violation(s), 8 isolator barrier violation(s)
```

Path `[1]` is **exactly** the OVP-01 divider named in
`SELV_ISOLATION_REDESIGN.md` §4 row 3 and `main.ato:434-435`: `R51`, `R52`,
`R53` are the three 430kΩ top resistors (`r_div_top1/2/3`), `R54` is the 10kΩ
bottom resistor (`r_div_bot`), and the reported path runs `dc_bus_plus`
(`+170V_BUS`) → 430k → 430k → 430k → the comparator's sense node → 10k →
`gnd` — a direct, unisolated, ~1.30MΩ resistive bridge from the HV half-bus
to SELV ground. Confirmed independently by grep against `modules.ato`:
`r_div_bot.p2 ~ power.gnd`, value `10000ohm`; `r_div_top1/2/3.value =
430kohm` each.

The eight isolator-barrier violations name the same underlying finding from
the other side: every declared isolator's own primary/secondary groups turn
out to be mutually reachable — via this same resistive network — even though
none of the isolators is itself internally defective. `aux_supply.psu`'s
own reported bridge is that identical R51→R52→R53→R54 chain (line 18 of the
run above), which is the clean, direct demonstration the task asked for:
*"so a human can see [the domains merge] immediately."*

### Path-finding mechanics, verified rather than assumed

Two problems surfaced and were fixed during construction, both caught by
direct measurement rather than assumed away:

1. **A naive star topology for multi-pin components manufactured false
   1-hop "shortcuts."** The first version of `build_graph` connected all of
   a component's pins through whichever pin happened to appear first in the
   netlist file. For the 5-pin OVP comparator (`U17`), this made its GND pin
   and its INP pin look like a direct 1-hop connection purely because of pin
   *file order*, which buried the real `r_div_bot` (10kΩ) resistor behind an
   equal-length but less informative route through the comparator IC.
   Fixed: `build_graph` now chains a component's nets in **pin-number**
   order.
2. **Even pin-order chaining left a genuine tie** (`U17`'s pin 2 happens to
   be `gnd`, adjacent to pin 3's `comp-inp` — a real pinout coincidence, not
   a bug), so `multi_source_shortest_path` was changed to a weighted 0-1 BFS:
   a genuine two-terminal component (weight 0) is preferred over an
   equal-hop route through an arbitrary pair of pins on a wider, multi-pin
   part (weight 1). This is what makes the report show the resistor-only
   path (`R51→R52→R53→R54`) rather than the electrically-real-but-less-legible
   `R51→R52→R53→[U17, the comparator]`. The IC route is never hidden — it is
   simply not preferred when a two-terminal-only route of equal or lower
   cost exists, and `find_independent_paths` additionally re-searches after
   removing each found bridge's edges, so unrelated crossings are reported
   as separate, independent findings rather than only the single globally
   shortest one.

**A third problem was caught by direct measurement, not code review:**
running the gate three consecutive times on byte-identical input produced
three different orderings of which bridge printed as `[1]`/`[2]`/`[3]`
(content and count were stable; order was not). Root cause: several places
iterated a Python `set` directly, and `str.__hash__` is randomized
per-process (`PYTHONHASHSEED`) unless pinned — so a tie between
equal-cost paths resolved differently across process invocations.
METHODOLOGY.md §5 requires exactly this kind of invariance check for
third-party oracles (`kicad-cli pcb drc` was found to vary run-to-run for
the same reason class); the same standard was applied to this script's own
internals. Fixed by sorting every set-derived iteration order before use.
**Verified:** three consecutive runs, plus two runs under explicit different
`PYTHONHASHSEED` values, now produce byte-identical output (`diff` exit 0
in all four comparisons).

---

## 3. Additional violations found beyond the named seed defect

Per instruction not to narrow the check to make it pass, and to report
extra findings as signal rather than noise:

| # | Crossing | Component(s) | Assessment |
|---|---|---|---|
| 1 | OVP-01 main comparator divider | `R51/R52/R53` (430kΩ×3) + `R54` (10kΩ) | Matches `SELV_ISOLATION_REDESIGN.md` §4 row 3 exactly. **Single-fault consequence, computed by hand**: if `R54` (the 10kΩ bottom leg) opens — a plausible SMD-resistor failure mode — the comparator's sense input and everything on the same node lose their voltage-divider return; the node is pulled toward `+170V_BUS` through the 1.29MΩ top leg, limited mainly by whatever leakage/loading remains on the SELV side. This is a "goes toward full bus voltage on a single fault" class of hazard, not a bounded steady-state leakage number. |
| 2 | OVP-01 ADC-sense divider (independent from #1) | `R58` (510kΩ `r_adc_top`) + `R59` (10kΩ `r_adc_bot`) | Matches `SELV_ISOLATION_REDESIGN.md` §4 row 4. Feeds `mcu.adc_v_bus` (`V_BUS_SENSE`) directly — the shortest single-hop crossing found (`+170V_BUS` → `R58` → `V_BUS_SENSE`, since `V_BUS_SENSE` is itself an MCU pin and therefore SELV by declaration). Same single-fault shape as #1: if `R59` opens, the MCU ADC pin is pulled toward the HV bus through 510kΩ. |
| 3 | Gate-driver bootstrap network | `D5` (neg-bias zener) + `C17` (boot cap) + `U8` (boot diode) | **New finding, not named in `SELV_ISOLATION_REDESIGN.md`.** This is the standard high-side bootstrap topology (charge `C17` from `+15V` through `U8` while `SW_NODE` is low; `U8` blocks reverse conduction while `SW_NODE` swings high) — textbook, and *functionally* correct. But none of `D5`/`C17`/`U8` is a certified reinforced/basic-insulation component; a diode's reverse-blocking voltage rating is a functional-operation guarantee, not an IEC 60335 isolation credit, and a shorted `U8` (a common real failure mode for a fast diode under reverse-avalanche stress) would tie `+15V` — which the design's own docs list as SELV and which also powers the RTD probe's reference domain — directly to the full floating `SW_NODE` potential. Reported here as an honest, caveated finding: a domain expert may reasonably judge this as accepted bootstrap-topology risk rather than a certification gap (it is not resistive/steady-state like #1–2), but it is not a *certified* isolator either, and the check's conservative model is correct to flag it under the same standard applied everywhere else in this project's audits. |

All three are reported by the check automatically (§2); none required
special-casing to surface, and none was suppressed to narrow the report.

**Empty-net bonus finding** (suggested during review): the check also
reports, informationally, every net record with zero connected pins — not a
domain violation, but a data-quality signal. Current netlist: 23 such
records, e.g. `gnd_ref` (a dangling field of the `ElectricPower` interface,
`interfaces.ato:77`, wired in some `ElectricPower` instances via
`dc_bus.gnd_ref` but not this specific unused one) and eleven `mcu-reference*`
/ `safety-*` stub nets from other unwired interface fields. Does not affect
the exit code.

---

## 4. Proof it PASSES on a correctly isolated topology

Given the real board currently has three independent, real, still-open
crossings (§3), constructing a "star join removed, now passes" fixture from
the real board is not honest — fixing only the aux-supply barrier does not
make the real netlist pass, and it should not, because the other two
crossings are real and independent. Two complementary proofs instead:

**(a) The isolator-specific proof, on the real board.** Every one of the
eight declared isolators is individually correctly modeled: `PS1` (aux
supply), `T1` (current transformer), and `U3` (the new ZCD opto) all show
their primary-group pins and secondary-group pins landing on genuinely
different raw nets (`PWR_RTN` vs. `gnd`, or `+170V_BUS`/`+15V` vs. `gnd`) —
confirmed directly from the netlist, independent of any graph traversal.
Each isolator's *own* barrier is only found "bridged" because of a *separate*
network-wide crossing (the OVP dividers / bootstrap network in §3), not
because the isolator declaration is wrong. This is exactly the auxiliary
supply fix the original star-join defect targeted, working as intended.

**(b) A minimal synthetic fixture, unit-tested** (`TestRunEndToEnd::test_clean_isolated_topology_passes`,
`scripts/tests/test_check_domain_partition.py`): a hand-built netlist with
one declared isolator (`aux.psu`, primary pins on `ac_l`/`hv_return`,
secondary pins on `v15`/`selv_gnd`) and no other components. Manifest
declares `HV: [ac_l, hv_return]`, `SELV: [v15, selv_gnd]`. Run:

```python
code = run(netlist, manifest, tmp_path, skip_freshness=True)
assert code == EXIT_OK   # 0
assert "PASSED" in capsys.readouterr().out
```

Measured: `PASSED` (exit 0). This isolates the one variable that matters —
a genuinely disjoint topology with a correctly declared isolator — from the
real board's unrelated, independently-real defects.

---

## 5. Proof it is not trivially satisfiable (anti-vacuous-truth, negative tests)

33 tests total in `scripts/tests/test_check_domain_partition.py`, all
passing (`uv run pytest scripts/tests/test_check_domain_partition.py -q` →
`33 passed`). The ones specifically targeting vacuity/false-negative risk:

| Test | What it proves |
|---|---|
| `test_empty_file_is_gate_error_not_silent_pass` / `test_empty_manifest_fails_closed_not_silently_passes` | An empty manifest file exits 5 (GATE ERROR), never 0. This is the exact failure mode named in the task brief ("no data therefore no violations") and in this project's own history (ten dead CI gates). |
| `test_manifest_with_no_domains_key_is_gate_error` / `test_manifest_with_empty_domains_dict_is_gate_error` / `test_domain_with_empty_net_list_is_gate_error` / `test_single_domain_is_gate_error` | Every way to declare "no real domain content" fails closed, not silently. |
| `test_net_declared_in_two_domains_is_gate_error` | A self-contradictory manifest (same net in both domains) is caught, not silently resolved either way. |
| `test_isolator_with_one_group_is_gate_error` / `test_isolator_pin_in_two_groups_is_gate_error` | Malformed isolator declarations (an isolator that isolates nothing; a pin claimed by two groups) fail closed. |
| `test_unmatched_instance_path_is_gate_error` | A declared isolator whose component no longer exists in the design fails closed — the domain boundary it protected may no longer be enforced by anything, and that must be loud, not silent. |
| `test_incomplete_group_coverage_is_gate_error` | A real, wired pin on an isolator that the manifest's pin-groups don't cover fails closed — "an isolator with an undeclared pin is a gap in the model, not a clean bill of health" (this is the single scenario closest to a real audit mistake: forgetting to account for one pin of a multi-pin isolator). |
| `test_declared_pin_not_wired_is_gate_error` / `test_declared_net_not_in_netlist_fails_closed` | Stale manifest entries (referencing a pin or net that no longer exists) fail closed rather than silently matching nothing. |
| `test_missing_netlist_fails_closed` / `test_missing_manifest_fails_closed` | Missing input files fail closed. |
| `test_stale_netlist_fails_closed` / `test_run_end_to_end_fails_closed_on_stale_netlist` | **The freshness gate.** A netlist that predates the newest `.ato` source file fails closed — checking yesterday's design and reporting "0 violations" is indistinguishable from a correct check on today's design otherwise, and this exact failure mode is called out in METHODOLOGY.md §5 as having hit this project six times in two days. |
| `test_missing_isolator_declaration_causes_visible_false_positive` | The other direction of the fail-closed contract: if a manifest *forgets* to declare a real isolator, the default "undeclared component conducts across all its pins" assumption makes a correctly isolated topology look shorted — a loud, visible false positive a human must adjudicate, never a silently missed real short. Verified: exit 3 (not exit 0) when `aux.psu`'s isolator declaration is removed from an otherwise-correctly-isolated fixture. |
| `test_shorted_barrier_fails_with_path` | The positive falsifier, in miniature: a synthetic fixture where an isolator's own primary and secondary pins share one net (mirroring `PS1` pins 2/4 both landing on `PWR_RTN` in the original star-join defect) fails with the shared net named in the output. |
| `test_multi_hop_path_is_reported` | A crossing that requires an intermediate net (not a same-net collision) is found and the intermediate hop + bridging component appear in the printed path — the "net-by-net path" requirement, not just a same-net check. |
| `test_undeclared_component_unions_all_its_pins` / `test_isolator_groups_are_not_unioned_across_barrier` | Direct unit tests of the two core modeling rules (fail-closed default conductivity; isolator groups never bridge). |

---

## 6. CI wiring, fail-closed

Added to `.github/workflows/python-tests.yml`'s `test` job, immediately
after the existing "Build electronics netlist" / "Run electronics
validation tests" steps (so the netlist is always freshly built in the same
job before this gate runs):

```yaml
- name: Domain-partition gate unit tests
  run: uv run pytest scripts/tests/test_check_domain_partition.py -v --tb=short

- name: Netlist domain-partition gate (galvanic isolation)
  run: uv run python scripts/check_domain_partition.py
```

**No `continue-on-error`.** Unlike several other gates in this workflow
that are currently soft-launched (`continue-on-error: true` pending a
2026-09-01 cutover), this gate blocks immediately: it is checking the
project's own highest-severity finding to date, and the task instructions
were explicit that a check catching this class of defect must be
merge-blocking, not advisory.

**Consequence, stated plainly:** merging this gate as-is will turn this CI
job red on `main`/PRs, because the real, open findings in §3 are real. That
is the intended, correct behavior of a fail-closed gate discovering a real
defect — not a bug in the gate. `elec/**` and `scripts/**` are already broad
path filters on this workflow's `push`/`pull_request` triggers, so no
additional trigger-path entries were needed for the new files.

Confirmed the workflow YAML still parses after all edits
(`python3 -c "import yaml; yaml.safe_load(open('.github/workflows/python-tests.yml'))"`
→ no error, job list unchanged).

---

## 7. UNVERIFIED

- **PCB-layout-level verification of any of these findings** (creepage/
  clearance, actual physical routing) is out of scope for a netlist-level
  check by construction; this check only asserts electrical-graph
  connectivity, not physical separation distance.
- **Whether the gate-driver bootstrap finding (§3 #3) should be modeled
  differently** (e.g. as an accepted, standard, non-certifiable functional
  connection rather than a flagged crossing) is a domain-expert judgment
  call this document states rather than resolves — reported honestly as an
  additional finding with its reasoning shown, not adjudicated one way.
- **Whether `V_BUS_SENSE`'s single-fault behavior (§3 #2) has been
  independently bench-verified** — the "pulled toward the bus voltage" claim
  is derived from the divider topology, not measured on hardware.
- **Full enumeration of every net in the design against the two domains** —
  the manifest declares the nets relevant to the domains actually audited so
  far (matching `SELV_ISOLATION_REDESIGN.md`'s own crossing survey); it is
  not a claim that literally every net in the ~160-net compiled design has
  been individually reviewed and assigned a domain.
- **Whether the CI job's `elec/build` cache (keyed on `hashFiles('elec/src/**')`)
  could ever let a stale netlist reach this gate in practice** — the gate's
  own freshness check (§2, mtime-based) is the actual fail-closed guarantee
  and does not depend on the cache behaving correctly, but the cache
  interaction itself was not separately measured under a simulated
  cache-hit-with-stale-artifact scenario.
