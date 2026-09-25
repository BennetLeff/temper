# Revision 25 native integration feasibility

## Result

No merged schematic is issued in this revision. The three requested inputs do
not currently form one native design that can be joined without inventing a
source/control binding or duplicating parts. A rendered schematic assembled
from the reference sheets would look more complete than the evidence permits.
This report preserves the concrete blockers and the minimum work needed to
resume the integration.

The checked inputs are immutable. No source fixture, PCB, or progress index was
changed.

## Inputs checked

| Input | Native form | Identity checked | Integration facts |
|---|---|---|---|
| Revision 11 full candidate | Atopile source plus compiled Atopile netlist; no KiCad schematic output retained in the revision directory | `default.net` SHA-256 `c9971a9475191749a6d67c50c6ae2425b468e64b0c23b1d2e412ca866887ad92`; top-level `.ato` SHA-256 `8491fb2fba480bcfa45713a0c2d9f67563bc6f197b727528c570d4939c345006` | The top-level makes AUX, return, HOT permit, ARM, logic5, control ground, and HV nets external signals. `aux_15v` directly feeds PFC VCC, PFC relay-drop/resistor network, OV/inhibit network, and the AUX connector. `aux_15v_return` joins `hv_minus`; `hv_minus` joins `control_gnd`. These connections must be kept as the source candidate defines them unless the source integration itself is revised. |
| Revision 19 corrected clamp | Standalone KiCad sheet, native netlist, pin/net TSV, ERC record | `clamp.kicad_sch` SHA-256 `3068f722f43ac1dc61452cc2ec181f7db153b14c555cfa6860eb79d697c930a5`; expected TSV SHA-256 `ca709e6d2a86c269ef830df8bbfe3f61563c3488be2a46ca495393a930b7b8e7` | The corrected graph puts R7.1 and D1 anode on `GATE_DRV`; D1 cathode stays on `CG`. Ports `AUX_RAW`, `AUX_PROTECTED`, and `HOT_GND` require explicit binding. `AUX_PROTECTED` cannot be treated as a new Rev11 net while the Rev11 consumers still hang directly on `aux_15v`. |
| Revision 16 reset/control | Standalone KiCad reset sheet and contextual components, native netlist, pin/net TSV | `reset.kicad_sch` SHA-256 `a87bdb095b994cbe36ef89918bdea7deb6b0ca51d955e69acdf40b937526d0cc`; expected TSV SHA-256 `e911835bddfc85383619bf3711cb6f3c43c1a8d317b67e3daae604f63d30e23c` | The 28-component fixture includes existing context and reuses both halves of its contextual HOT latch plus a final enable gate. The sheet's U6/U7 references are local; copying them into Rev11 without identifying/renumbering the actual matching Rev11 instances risks duplicating the latch and enable. The map also assumes an ISO7741FDWR four-channel allocation and decoded session signals not implemented by the Revision 11 simple ARM/PERMIT boundary. |

The pin-level contracts and open boundaries are summarized in
[`../interface-integration-24/control-audit.md`](../interface-integration-24/control-audit.md).
Revision 11's build evidence and interface contract are in
[`../interface-defaults-11/README.md`](../interface-defaults-11/README.md) and
[`../interface-defaults-11/INTERFACE-CONTRACT.md`](../interface-defaults-11/INTERFACE-CONTRACT.md).

## Why the native join stopped

1. **Revision 11 is not a KiCad sheet to compose.** Its source of truth is
   Atopile, and its saved output is the compiled netlist. The repository's
   schematic generator consumes the Atopile netlist and emits the project
   schematic hierarchy; it does not merge arbitrary native KiCad sheets back
   into that Atopile design. Hand-drawing a parallel integration sheet would
   create a second connectivity authority, contrary to the repo's documented
   generated-schematic workflow.
2. **The source build could not be run here.** `atopile` is not installed in
   PATH. `uv run --project elec ato --version` first failed because the default
   uv cache under `/Users/bennet/.cache/uv` is not accessible in this sandbox.
   Retrying with `UV_CACHE_DIR=/tmp/temper-uv-cache` reached package resolution
   but could not fetch `rich==14.2.0` because network DNS is unavailable. No
   Atopile source change or derived output could therefore be compiled.
3. **Clamp integration changes the established AUX boundary.** The Rev19
   clamp's `AUX_RAW` and `AUX_PROTECTED` ports imply inserting the clamp between
   the producer and every Rev11 AUX consumer. Rev11 presently has a single
   `aux_15v` net serving those consumers and the external connector. The
   producer, rail-capacitance/load contract, and source fault waveform are
   unresolved. Connecting only the connector through the clamp, or tying
   `AUX_PROTECTED` directly to `aux_15v`, would either bypass the clamp or
   alter the source topology without authority.
4. **The control fixture selects a different interface.** Rev11 exposes
   external `hot_arm` and maintained `hot_permit` into its existing local
   protection/latch path. Rev16 adds an independent reset/watchdog health
   AND, a source permission latch, ISO7741FDWR channel allocation, decoded
   session/start signals, and HOT watchdog clear logic. There is no selected
   producer/decoder or contract choosing this architecture over Rev11's
   simpler boundary. Importing the reset sheet wholesale would duplicate
   existing contextual latch/enable parts; wiring only its labels would
   falsely imply those producers exist.
5. **The domains cannot be inferred from labels.** Revision 11 explicitly
   ties AUX return/HV minus/control ground together on the HOT side. Revision
   16 has separate `SELV_GND` and `HOT_GND`, with U4 as the drawn barrier.
   Net names alone do not authorize changing or joining those domains.

## Tool attempt

`kicad-cli version` reports KiCad 10.0.4. It is available for future native
export/ERC/render work after there is an authoritative merged source. The
Atopile invocation and its failure are recorded above. No KiCad ERC, netlist,
or render was generated for Revision 25 because no merged graph was authored.

## Minimum closure path

The current engineering target is **latched safe shutdown followed by
deliberate re-arm**. It is an acceptance condition, not a demonstrated result:
the eventual implementation must show that loss of AUX disables switching and
the relay, and that source restoration alone cannot restart either. The
existing Rev11 model has a known ARM-high reconnection restart case, and the
Revision 20–23 clamp simulations do not prove actual gate turnoff. Keep this
target explicit in the eventual fixture's unresolved verification ledger.

1. Decide whether Rev16's session/health/isolator architecture replaces or
   extends the Rev11 ARM/PERMIT producer contract, and identify the exact
   existing Rev11 latch/enable instances by component identity and pins. The
   safe-shutdown/re-arm target does not by itself select that implementation.
2. Select the source boundary and state whether LT4363 is actually inserted
   between the source and every existing AUX load; provide source voltage,
   fault waveform/impedance, return reference, and protected-rail capacitance
   and load limits. Keep the Revision 19 clamp graph's corrected gate pins.
3. Make those decisions in a fresh Atopile source candidate (or explicitly
   designate another single source of truth). Bind every producer and rail;
   retain unimplemented ports as typed external signals rather than adding
   power flags or fabricated drivers. Keep the SELV/HOT grounds distinct.
4. Build that source with Atopile, regenerate its KiCad output, export a native
   netlist, compare the `(reference,pin)` connectivity partition against the
   Atopile netlist, audit manufacturer pin functions and forbidden cross-domain
   connections, run ERC, retain named open-port findings, then render and
   visually review the resulting sheets.

Until those source/control decisions are made, Revision 11 remains the latest
compiled full candidate, Revision 19 remains a corrected standalone clamp
prototype, and Revision 16 remains a reset/control reference fixture. None is
promoted by this report, and no hardware or electrical qualification is
claimed.
