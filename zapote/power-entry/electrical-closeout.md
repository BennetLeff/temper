# Power-entry electrical closeout

Execution contract, 2026-09-16, starting at `7f506ba86`.

The next milestone is an explicit electrical handoff to the auxiliary-power
unit. It is not powered qualification or integration of the legacy cooker.

1. Check the single PFC bus and HOT bias/control connector contract against
   compiled source; retain the separate source/native pin and saved-board
   binding checks. This does not establish package geometry correctness.
   Make missing external bias, isolated permit,
   precharge sequencing, and low-line foldback visible checked obligations.
   The legacy split-bus auxiliary circuit is not an accepted consumer.
2. Reuse the existing switching waveforms and native copper graph to expose
   via, pad and shunt stress separately. Preserve exact versus bounded currents;
   never substitute equal sharing, package width or arbitrary current density.
3. Prevent whole-net extents from masquerading as switching-loop measurements.
   Record the required physical endpoint paths and the missing return-path,
   commutation-loop, EMI and shutdown evidence. No invented acceptance limits.
4. Run regression mutations and the common maintained-unit suite, retain the
   actual reports, review the diff, and commit the resulting code and evidence.

Acceptance requires regressions for connector polarity/reference mistakes,
missing evidence, physical identity faults and misuse of unscoped loop bounds.
Existing GBU trace failures must remain failures; the GBJ alternative must not
be promoted through assumed current sharing. No PCB repair is justified by
an unknown rating or a misleading whole-ground-net bounding box.

Remaining model inputs include finished via/barrel plating, solder/package
thermal paths, pad minimum cuts, parallel copper current distribution,
worst-case shutdown timing, and fault/inrush behavior. These are software/model
gaps until addressed; bench qualification is a separate obligation.

Next standalone unit: auxiliary power, with a selected input architecture,
separate HOT and control-side supply domains, a complete load/startup budget,
and source-backed insulation and transient limits. Reusing the old half-bus
input circuit on the full PFC bus is prohibited without redesign.

## Implemented checks and remaining models

`zapote-erc::pfc_interfaces` rejects renamed HOT references and split-bus
output labels, even when source/native topology would agree. Five required
rule IDs expose the reviewed pin boundary and four unfulfilled external
obligations. Removing their hook fails the common runner's coverage check.

The PFC report now lists vias on modeled power nets with physical UUIDs and
determined graph currents or conservative envelopes. It also computes nominal
shunt stress from the reviewed resistance and existing switching waveform:
15 A RMS, 23.232 A peak, 2.25 W mean and 5.397 W peak. These are model results,
not measurements; temperature, tolerance, pulses and package limits remain
unqualified. Pad attachment chords remain distinct from pad/barrel capacity.

The switching checker retains the whole-net extent as a labeled diagnostic,
and cannot use it to PASS or FAIL a loop-area bound. It identifies the gate
resistor path and the separate, still-unmodeled boost commutation path.
Endpoint-restricted physical geometry, inductance and shutdown timing still
need implementation and independent validation.

The generic P1 adapter still has missing via/plating/pad ratings. This change
exposes the available PFC evidence in the common report; it does not complete
all electrical models or qualify either board candidate. The maintained GBU
bridge necks still fail the current screen. The GBJ alternative remains a
separate conditional candidate.

The ideal CCM waveform is a stress-model operating point, not the input-power
budget: at 15 A true RMS it yields 1796.416 W with ripple included and an
in-phase fundamental. The separate PF 0.99 budgeting assumption yields 1782 W
at 120 V. Neither establishes actual controller PF, low-line regulation, or
every waveform at PF 0.99. The shunt's 2.25 W mean loss follows from 15 A true
RMS and 10 mΩ regardless of PF. Do not silently rescale the pinned waveform
or treat either calculation as measured cooker output power.

The common runner authenticates the fresh native manufacturing receipt's
extractor, board and census, then checks its complete byte hash before sharing
one immutable buffer with PFC and thermal checks. Supplying an arbitrary
receipt with a matching `board_sha256` to the lower-level PFC function is not
an authenticated geometry replay. Its caller must establish provenance.
