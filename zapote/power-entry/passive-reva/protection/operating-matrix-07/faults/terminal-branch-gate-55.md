# Terminal-branch gate 55

Date: 2026-09-21. This is a read-only readiness review of the prepared
DIODE-SHORT and BOTH-SHORT graph experiments. It does not run ngspice and does
not grant a fault acceptance or a hardware claim.

## Decision

**READY_FOR_TERMINAL_GRAPH_EXPERIMENT**, conditional on the normal-prefix gate
in `faults/fault-matrix.md` and on validating the prepared trace endpoint and
event receipt. The compact manifests themselves remain
`PREPARED_UNEXECUTED`; they are not evidence merely because the topology is
well-defined. The experiment is graph-level only.

## Exact terminals and healthy graph

The retained passive source names the selected C3D20065D as a three-lead
dual-die common-cathode package: A1 and A2 are separate anodes and K is the
common cathode (`../f2-open-01/source-01/elec/src/power_entry_passive_reva.ato:84-93`,
SHA-256 `dd31c0addd5a5a5764955efca44d50d6fe89747f88c937e4c127398349b701d8`).
Its graph connects both anodes to the MOS drain and K to the positive bus at
lines 370–377. Thus the healthy diode graph is two parallel `sw -> vd` diode
branches with a common cathode; there is no externally accessible isolated
die branch after the two anodes are tied together.

The prepared DIODE-SHORT netlist makes that graph explicit with
`Dboost1 sw d1_path`, `Vdboost1sense d1_path vd 0`, and the matching second leg
at lines 30–33 of
`faults/settled-compact-prep-24/prepared/DIODE-SHORT/case.cir` (SHA-256
`d5a78e2c878447110a13c54cc3052b3dff7e862dc3e79a5fbd8e973257ac5f78`).
Because the zero-volt sense source forces `d1_path == vd`,
`Sdiodeshort sw d1_path ...` at line 89 is a short between the **boost switch
node sw (common diode anode terminal)** and the **common-cathode node vd**.
It is a valid terminal-level diode-side short graph. `i(Vdboost1sense)` is a
probe of that modeled branch; it is not a separately measurable A1 die current
or a package current-sharing result.

The same deck keeps the F2 path as `Sf2 vd f2_path` plus
`Vf2sense f2_path vb` at lines 53–56. F2 is therefore the modeled `vd`–`vb`
series path and remains a separate branch; it is not part of the diode
terminal short.

BOTH-SHORT adds `Sswfail sw channel_source ...` at line 90 of
`faults/settled-compact-prep-24/prepared/BOTH-SHORT/case.cir` (SHA-256
`c35139cff49f8f43db43a4dca9cff13c06c0289150b09dab12ba5aff29ffcb51`) while
retaining the same `Sdiodeshort` at line 93. `Msw sw gate channel_source
channel_source` and its zero-volt `Vchannel channel_source 0` probe are at
lines 35–36. Therefore the second exact short is the MOS **drain sw to source
channel_source** terminal pair, independent of gate state. BOTH-SHORT is the
combination of the common-cathode diode-terminal short and the MOS D–S short.

The two compact manifests bind these decks as DIODE-SHORT and BOTH-SHORT,
retain four branch/marker extras, and explicitly say no simulation/raw trace
or acceptance exists (`.../prepared/DIODE-SHORT/manifest.json`, SHA-256
`fd5c7f9e9703a5d0004bcd523798644068d0b378081361580bcda5c29b67baa9`;
`.../prepared/BOTH-SHORT/manifest.json`, SHA-256
`92345035c765b9132540e067b1ffe3ce06e4845095671328700386502dc0479b`). Their
compact-pacer records also require checking the actual final sample because
the predicted endpoint marker differs from the finite-materializer endpoint.

## Checker precedence and category

The frozen checker is `faults/fault_checks.rs` (SHA-256
`a94f3a7e5ac5bcae67d94a53afacf8338567eaf8b1870b2bf8db12121f25bc66`). Its
ordering is material to the gate:

1. `parse_trace` first requires the exact 17-column header, finite values,
   strictly increasing timestamps, bounded gaps, start at zero, at least 100
   rows, and the declared endpoint (`fault_checks.rs:114-166`). Invalid or
   incomplete transport is a failure, not a graph result.
2. `check` then rejects missing scenario bounds/bypass and applies all-row
   `vd`, `vb`, `sw`, `gate`, and `Lboost` screens (`:175-199`). A node-screen
   violation therefore precedes any short-fault category.
3. It requires the detector edge in the declared event window, the F2
   closed-to-open transition only for F2 cases, and a stable healthy prefault
   window (`:201-243`).
4. For SW-SHORT and BOTH-SHORT, any channel current above the frozen
   `channel_off` limit returns `ProtectionGap`; even if it is below that limit,
   the failed-short state still returns `ProtectionGap` and can never earn a
   protection `Pass` (`:246-260`). A `Fail` from an earlier screen or missing
   event remains the higher-precedence outcome.
5. DIODE-SHORT follows the ordinary latch-off/current-cessation path
   (`:262-298`) and could return the checker’s model-level `Pass`, but the
   checker does not screen `i(Vdboost1sense)`, `i(Vdboost2sense)`, `i(Vf2sense)`
   or branch energy. Such a pass cannot be read as a diode, package, fuse, or
   thermal result.

The required interpretation is therefore: DIODE-SHORT may answer whether the
healthy controller reaches its scripted off state while the modeled diode
terminal is shorted; BOTH-SHORT is a graph stress case whose intended outcome
is `ProtectionGap` if it reaches the short-state branch, subject first to the
global node/event screens. Neither case permits individual-die allocation,
package sharing, short-circuit withstand, F2 clearing, arc/restrike, or SOA
claims. No individual diode rating or current split is inferred from the
instrument-created `d1_path`/`d2_path` nodes.

Execution remains conditional on carrying an accepted contiguous normal prefix
into the fault case, using the exact manifest/source hashes above, and storing
the branch currents and endpoint/event checks in the receipt. These prepared decks intentionally run from cold start through a late
fault. Launching them unchanged is appropriate once runtime gates pass; their
measured 0-to-650ms normal prefix must independently pass before the later
fault can be described as arising from an accepted operating condition.
A short zero-state smoke run would not establish this.

## Parent interpretation corrections

The strict parse_trace description above concerns the standalone legacy CLI.
The reviewed runner45 instead uses the event-aware adapter13 and validator22:
all rows undergo finite/order/global-gap and node checks, while the frozen
check function receives a bounded suffix after equal-time predicate checks.
Original repeated-time rows remain retained. A legacy strictly-increasing
parser rejection therefore does not by itself invalidate the declared
event-aware campaign result; the actual pipeline and all its exits govern.

In both of these exact prepared decks, Vf2ctl is constant5V. F2 remains
closed for the whole run; neither experiment commands it open. Its presence
in the graph does not demonstrate even scripted bank interruption in these
cases. Any discussion of what an opened F2 could isolate is a separate
topology inference, not an outcome of the prepared DIODE/BOTH stimulus.

The frozen ProtectionGap message says current retained "after latch", but
its channel_peak accumulation begins at the detector edge and the failed-short
branch returns before checking for any latch-off witness. Report actual
post-detector current under that name and the categorical gap separately;
do not infer a latch event from the message text.

Parent checkpoint77 metadata correction: DIODE manifest digest above was transcribed incorrectly; replaced using the actual prepared file SHA-256. Prior text preserved. No graph or checker conclusion changed.
