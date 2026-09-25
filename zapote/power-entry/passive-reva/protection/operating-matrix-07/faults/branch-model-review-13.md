# Branch-model review 13: diode and switch short experiments

Status: **model-experiment disposition only; no fault deck is approved for execution**.
This review reads the prepared netlists and the held campaign contract. It does not reopen the settled normal-source or controller decisions and makes no hardware or fuse qualification claim.

## Graph actually implemented

The prepared fault decks begin from the hysteretic candidate (`prepared/*/cold.cir`) and add branch sense sources and ideal short switches in `case.cir`. The normal power path is:

```text
Vac -> Rsource (0.25 ohm) -> Rntc (10 ohm; relay can bypass it)
    -> bridge -> Rwind (20 mΩ) -> Lboost (180 µH) -> sw
    -> Dboost1 || Dboost2 -> vd -> F2 switch (15 mΩ) -> vb
    -> Cbank 2240 µF / load
```

The local reservoir is `Clocal(vd,0)=19.8 µF`; the bank is `Cbank(vb,0)=2240 µF`. `F2` is a candidate net inside these prepared decks, not a component in the retained passive ATO. The retained ATO still connects the diode cathode and bulk capacitors directly to the same positive net; the VD/VB split is a proposed next schematic, as documented in [`faults/interruption-boundary-09/README.md`](interruption-boundary-09/README.md).

The prepared deck makes each diode branch observable by inserting an ideal zero-volt source:

```text
Dboost1: sw -> d1_path -> Vdboost1sense(0 V) -> vd
Dboost2: sw -> d2_path -> Vdboost2sense(0 V) -> vd
```

The MOS source is similarly measured through `Vchannel(channel_source,0)=0 V` and the body diode through `Vbody(0,body_anode)=0 V` plus `Dbody(body_anode,sw)`. Those sources do not provide isolation or impedance; they only expose branch current. With intrinsic MOS diode suppressed in the retained level-1 model (`IS=1e-40`), `i(Vchannel)` is the channel branch and `i(Vbody)` is the explicit body-diode branch.

## What the held shorts connect

### DIODE-SHORT

`Sdiodeshort sw d1_path dshort_ctl 0 SWDIODESHORT` is in parallel with `Dboost1`. When its PWL control rises, it creates a roughly 1 mΩ path:

```text
sw -> Sdiodeshort (1 mΩ) -> d1_path -> Vdboost1sense -> vd
```

The other Dboost leg remains a diode. If the MOS is on, both the source/inductor path (`AC bridge -> Lboost -> sw -> short -> vd`) and, while F2 is closed, the bank path (`Cbank/vb -> F2 -> vd -> short -> sw -> Msw/channel -> 0`) can contribute. When the healthy MOS gate is removed, the controller can stop the controlled channel, but the shorted branch itself has no gate. `i(Vdboost1sense)` is retained in the supplemental trace; the fault checker does not screen or integrate that branch current.

**Physical identity limitation:** the retained C3D20065D is a dual-common-cathode part whose two anodes are intentionally paralleled in the source topology. There is no externally accessible `d1_path` versus `d2_path`; those nodes are created only by the ideal sense sources. Because `Vdboost1sense` forces `d1_path=vd`, the added switch is nevertheless a direct `sw`-to-`vd` terminal short. A shorted die would short the shared package terminals and would shunt the healthy parallel die. The model may therefore test the **terminal-level** short graph, but `i(Vdboost1sense)` must not be interpreted as an independently measurable die current or a package current-sharing result.

Disposition: **GO for a terminal-level model experiment** after an accepted normal prefix, with no qualification verdict. It is **NO-GO for individual-die current allocation, die thermal stress, or package-failure claims**.

### SW-SHORT

`Sswfail sw channel_source swfail_ctl 0 SWFAIL` is in parallel with `Msw(sw,gate,channel_source,channel_source)`. When asserted it creates:

```text
sw -> Sswfail (1 mΩ, gate-independent) -> channel_source -> Vchannel -> 0
```

This is a useful graph-level failed-channel surrogate. Gate/q/en transitions cannot open this parallel branch. In the source-side path, AC bridge and `Lboost` can still feed the short. A healthy Dboost diode is reverse-biased by a positive `vd`/`vb`, so this state alone does not provide a direct bank-to-ground path through Dboost; that distinction must not be lost in a generic “short fault” label.

Disposition: **GO for a topology-only model experiment** once the normal-prefix/restart contract is satisfied; expected checker classification is `PROTECTION_GAP`, never a protection pass. The 1 mΩ value is an assumed numerical surrogate, not a measured failed-MOS resistance.

### BOTH-SHORT

BOTH-SHORT combines the two branches:

```text
vb/Cbank -> F2 (15 mΩ) -> vd -> Sdiodeshort (1 mΩ) -> sw
         -> Sswfail (1 mΩ) -> channel_source -> Vchannel -> 0
```

`Sdiodeshort` still targets the instrument-created Dboost1 branch, but because it is a low-ohmic branch across `sw`–`vd`, the assembled graph behaves as a diode-side terminal short for this experiment. The bank/local capacitors and the source/inductor can feed the failed channel while F2 is closed. The local `Clocal` is on the diode side of F2, so its stored energy can still circulate through the short after F2 opens; F2 can only interrupt the bank-side contribution. Gate-off has no interruption credit; only the F2 element is in series with the bank branch.

Disposition: **GO as a graph-level simultaneous-short stress experiment** after the accepted normal prefix. Earlier node-screen violations can produce `FAIL`; otherwise the failed-short classification is `PROTECTION_GAP`. Gate/q/en state cannot earn a protection pass. F2 clearing, arc extinction, let-through and package failure dynamics remain unqualified.

## Ideal elements and controls

All three short/F2 mutations use ideal controlled switches with finite nominal resistance and no physical failure dynamics:

```text
SWFAIL       Ron=1 mΩ, Roff=1e12 Ω, Vt=2.5 V, Vh=0.1 V
SWDIODESHORT Ron=1 mΩ, Roff=1e12 Ω, Vt=2.5 V, Vh=0.1 V
SWF2         Ron=15 mΩ, Roff=1e12 Ω, Vt=2.5 V, Vh=0.1 V
```

The controls are ideal PWL voltage sources with a 1 ns edge. `fault_inject` records the control voltage (or `max` of the two controls), not the actual switch branch current or a physical fault sensor. Thresholding it at 2.5 V gives a timing marker; the switch's hysteretic turn-on is around 2.6 V. `Vchannel`, `Vbody`, `Vdboost1sense`, `Vdboost2sense`, and `Vf2sense` are ideal zero-volt probes. They provide no package lead inductance, contact resistance, arc voltage, current limiting, diode recovery, or fuse thermal state.

The plant also retains a generic level-1 MOS and generic DBOOST/DBODY models, ideal capacitors, and a single 180 µH inductor with 20 mΩ winding resistance. These are suitable for a bounded graph experiment only; they do not establish vendor I/V, short-circuit withstand, avalanche, C3D20065D sharing, or STW65N65DM2AG failure behavior.

## Important execution boundary

The checked-in `prepared/*` examples use `TSTOP=20 µs`, zero initial conditions, and rails that rise at millisecond times. They are deliberate **transport/materializer smoke fixtures**, not full fault stimuli: an as-written run has no accepted armed/healthy prefix, no charged 2240 µF bank, and no meaningful stored-energy short test. A clean solver exit from one of these tiny fixtures cannot establish protection behavior.

The full campaign materializations use the accepted cold-start source and long horizons (for example, the runbook's `.662 s`/`.682 s` cases), then carry the contiguous measured prefix/restart states into the fault mutation. The campaign contract is recorded in [`faults/fault-matrix.md`](fault-matrix.md) and [`faults/campaign-09-runbook.md`](campaign-09-runbook.md). Until that contract is met, DIODE-SHORT, SW-SHORT, and BOTH-SHORT remain `PREPARED_UNEXECUTED`.

## What the checker measures

The 17-column fault checker checks finite/order-complete rows, `vd`, `vb`, `sw`, `gate`, `Lboost`, detector rising edge, q/en/gate/channel-off timing, and retained-off behavior. It reports `i(Vchannel)` as channel-path current (including the parallel failed-short branch in those cases) and `i(Vbody)` as explicit body-diode current; the adapter retains F2 and both diode sense currents in its supplemental output. Source phase is a separate runbook check.

The checker does **not** prove that the diode branch is a physically separable die, does not screen `i(Vf2sense)` or `i(Vdboost1/2sense)` against a current/energy limit, does not measure F2 terminal voltage or arc/restrike, and does not integrate capacitor discharge or I²t. It also does not verify that the recorded AC voltage is at the requested crest/zero; the runbook's source-phase preflight does that. A DIODE-SHORT `PASS` would therefore mean only that this healthy, controllable channel reached the scripted checker off state in the surrogate graph. For SW-SHORT/BOTH-SHORT, `ProtectionGap` is the intended categorical result **when the earlier global node screens pass**; an over-limit `vd`/`vb`/`sw`/`gate`/`Lboost` is returned as `Fail` before the failed-short classification. Neither result is a measured fuse result.

## Go/no-go summary

| Experiment | Model-only disposition | What it can answer | What remains unclaimed |
|---|---|---|---|
| DIODE-SHORT | **GO terminal-level graph; NO-GO die-level claim** | Effect of a shared `sw`–`vd` diode-terminal short on controller/channel traces | Individual-die current allocation, package sharing/thermal stress, diode energy, F2 interruption |
| SW-SHORT | **GO after accepted prefix** | Whether controller state changes while a gate-independent 1 mΩ channel remains | Failed-MOS resistance/inductance, silicon SOA, interruption |
| BOTH-SHORT | **GO graph stress after accepted prefix** | Whether bank/local/source paths feed the combined low-ohmic loop and checker classifies the gap | F2 clearing, arc/let-through, dual-die package behavior, hardware safety |

No prepared case should be promoted from `PREPARED_UNEXECUTED` without the accepted normal prefix, explicit fault-state identity, branch-current retention, and a bounded checker receipt.
