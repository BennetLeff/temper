# Revision 17 — component-selection constraints and producer binding

This unit resolves the known protected-AUX capacitor census and identifies the
existing standalone interlock as the watchdog producer to consider. It does
not adopt new parts or alter the revision16 schematics. Exact part selection
is waiting for the PCBParts/Zenode connection the user chose to supply.
The full compiled power-entry candidate remains revision11 /136 components.

## Capacitor selection now has the complete known load list

| Direct protected-AUX item | Nominal value | Source |
| --- | ---: | --- |
| TPS54202 VIN bypass | 10uF | `controller-integration-06/supply/source/hot15_logic5_supply.ato:145` |
| UCC28180 VCC bypass | 1uF | `interface-defaults-11/source-candidate/elec/src/power_entry_pfc_control_candidate.ato:341` |
| UCC27511A local bulk | 1uF | `interface-defaults-11/source-candidate/elec/src/power_entry_f2_shutdown_revb.ato:575` |
| UCC27511A HF bypass | 0.1uF | same file:571 |
| Proposed LT4363 output bulk C4 | 220uF target | `interface-capture-16/clamp.kicad_sch` |

The known bypass sum is12.1uF nominal, or232.1uF including C4. This is a source
census for the intended integrated rail; those blocks are not yet a single
compiled graph. The pre-clamp LDO47uF and LT4363 VCC bypass are upstream.
HOT5 output/bypass capacitors, BOOT-to-SW capacitance, compensation and timer
capacitors are not directly in parallel with the protected output. Their
charging nevertheless contributes load current through their respective circuits.

Revision16's12uF maximum was explicitly hypothetical; it is not a bound for
this12.1uF nominal assembly. Until exact parts are known, conservatively include
all four direct bypasses in the ceramic-ratio screen. The1uF controller capacitor
already has a source MPN (`C0805C105K5RACTU`); the other generic values and every
part's applicable effective min/max still need verification. Do not replace
that known MPN merely because a worker described all capacitors as generic.

The [LT4363 output-capacitance requirement](https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf)
remains `Cbulk,min >= max(22uF, 10*Cceramic,max)`, with low ESR and placement near
the pass-device source/output. Revision16 also allocated no more than300uF
**total effective output capacitance**. These lower and upper requirements
must be checked together. “Larger bulk is safer” is not a valid selection rule.

`selection_screen.rs` computes a conditional nominal-value window, using
`bulk_nominal_min=max(22,10*Cceramic,max)/bulk_min_factor` and
`bulk_nominal_max=(300-Cother,max)/bulk_max_factor`, with capacitances in uF.
The retained CSV shows both the previous hypothetical example and the real
nominal census under explicitly hypothetical tolerances:

| Assumptions, not part specifications | Permitted nominal bulk window | Consequence |
| --- | ---: | --- |
|12.1uF bypasses each at+20%; bulk±20% initially |181.5–237.9uF |220uF fits this initial-only screen |
| Same bypass maximum; bulk has an additional independently specified±20% endurance change |226.875–198.25uF |No nominal value satisfies both requirements |

Separate initial tolerance and endurance factors multiply only when the exact
manufacturer specification defines them separately. Do not double-count a
combined guarantee or assume that every electrolytic has±20% endurance drift.
These rows show what to check; they do not reject every220uF part. Exact ESR,
ripple-current duty, lifetime, temperature, bias, and C3 effective1.35uF minimum
remain procurement acceptance fields. If the window is empty for selected
parts, revisit the300uF allocation and gate/startup screen together.

## Startup review correction

The [TPS54202 Rev C](https://www.ti.com/lit/ds/symlink/tps54202.pdf) table on
printed page5 was rendered and inspected; the PDF and page image are retained.
EN rising1.21V is **typical**, not a specified minimum.1.28V is maximum.
EN input0.7uA, hysteresis current1.55uA and soft-start5ms are typical values.
The previous source's1uA bias allowance is therefore an assumption, not a
manufacturer maximum.

The retained820kR/100kR divider delays buck enable to approximately10.6V using
nominal resistance,1.21V and the0.7uA current source. That is an illustration,
not a guaranteed startup threshold. Independently, VIN UVLO rising is3.9–4.4V
and falling3.4–3.9V. Thus the worker's suggestion that this normally functioning
buck starts switching in the LT4363's below3V foldback region is unsupported.
Do not add an extra sequencing circuit on that premise. Quiescent/leakage
loads and input-cap charging still exist below UVLO; their full-corner currents
need bounding. Higher-voltage buck start, output charging and PFC/driver turn-on
can still challenge the source/current limit. No integrated startup result is
claimed from the5ms typical soft-start datum.

## Reuse the standalone interlock, not the legacy board symbol

The current standalone unit is `zapote/interlock`, sourced from
`elec/src/interlock_unit.ato`. Its25-component candidate includes a
TPS3823-33DBVR, a1kR WDI pulldown and latched permission. Its J2 interface is:

| J2 pin | Existing signal | Integration use |
| --- | --- | --- |
|1/2 | SELV3V3 / SELV_GND | Same SELV reference as source-side reset fixture |
|3 | WDI | Source-host heartbeat; support the existing1kR pulldown current |
|4 | RESET_N | Deliberate interlock rearm request; not a reset-good level |
|5 | SENSOR_LIVE | Independent sensing validity; producer still required |
|6 | PERMIT | Candidate producer of revision16 INTERLOCK_PERMIT |
|8 | WDT_RESET_N | Supervisor diagnostic; do not directly attach revision16's10kR health pulldown |

The source already gives
`ALL_GOOD = no_faults AND SENSOR_LIVE AND WDT_RESET_N`; the latch clears when
ALL_GOOD is low. Therefore J2.6 PERMIT already includes the interlock watchdog's
fault handling. If J2.3 is explicitly assigned to the source MCU's heartbeat,
this existing path can perform the source-watchdog function. A second raw
watchdog input is not automatically required. The next reset revision should
choose explicitly between reusing that aggregate path and keeping a separately
buffered watchdog observation for additional fault coverage. No gate is removed
from revision16 yet, and no independent/redundant-channel claim follows from
sharing this producer.

[TI TPS3823 Rev O](https://www.ti.com/lit/ds/symlink/tps3823.pdf) guarantees its
RESET high-level datum at only30uA source current for the-33 device. A10kR
pulldown needs about200uA just to reach a2V logic high, before existing loads.
The worker's proposed direct fanout is therefore rejected as unqualified;
“push-pull” does not imply a strong CMOS output. Either rely on the already
buffered/latched PERMIT path or design a low-load diagnostic buffer with a
complete powered/unpowered and missing-wire analysis.

Watchdog timeout is0.9–2.5s; reset release delay120–300ms under the specified
conditions. The existing interlock recommends at most400ms between WDI falling
edges. Preserve its1kR pulldown: an unconnected WDI can disable this watchdog.
None of those timings establishes an acceptable whole-cooker stop interval.
The source reset contract must separately cover MCU reset while its supply
stays valid; a supply supervisor alone cannot observe every internal reset.
SOURCE_RESET_GOOD, HOT_WATCHDOG_GOOD, rearm sequencing and decoder/level
translation remain unresolved physical producers.

The legacy `elec/src/components.ato` TPS3823 and
`components/TPS3823/TPS3823.kicad_sym` reverse RESET/GND relative to TI. The
standalone interlock uses the correct local definition (RESET1/GND2), and its
MODEL.md already documents the legacy discrepancy. This is not a newly found
regression and is not repaired by reusing the standalone unit. Do not import
that legacy symbol into this candidate. The136-component power-entry candidate
does not contain this watchdog; it belongs to the separate interlock unit.

## Evidence and next action

Eight focused Rust checks pass, including invalid-bound rejection, contradictory
capacitance windows and the diagnostic-load counterexample. These verify the
arithmetic only. Frozen revision16 and its input hashes are checked in the
receipt. No whole-cooker, board, timing or physical qualification is claimed.
Both Luna handbacks are retained as unaccepted raw review material; the
corrections above are the parent-reviewed result.

Once PCBParts or Zenode is available, populate `selection-requirements.md` with
exact part evidence, resolve package constraints, and re-run the capacitor
window. Then produce the next integrated reset drawing using the selected
producer binding, rather than adding a duplicate watchdog by default.
