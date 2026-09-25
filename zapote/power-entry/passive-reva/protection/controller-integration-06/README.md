# Controller integration 06 — conditional simulation milestone

We now have a feedback-driven power-stage simulation that detects an opened F2,
latches the driver off, and puts the PFC controller into standby. It replaces
the earlier fixed-duty PWM stimulus. The supply candidate and conditional
current/energy calculator are implemented separately, with reproducible checks.
This is progress toward the operating-envelope plan, not completion of its full
line/load/fault matrix or qualification of a physical circuit.

The work is local to this experiment in `/private/tmp/temper-pkgs-1-4`, based on
`5dde29ab3e2f1223c2d33c129ced2cf647238307` with inherited uncommitted artifacts.
The user has simulation only. Experiments04/05 and their source inputs remain
frozen; `receipt.json` binds this experiment's final bytes and source identities.

## Delivered work and acceptance boundary

| Plan item | Delivered | Remaining condition |
|---|---|---|
| A3, node limits | Separate VD, VB, VDS, diode and VGS records; distinguish nominal trip points, chosen screens and part ratings | Installed transient/duration/temperature limits are not fully established |
| A4, current and energy | Rust forward/inverse envelope calculator with independent circuit-equation and energy checks | Reachable fault current, L(I,T), controller delay and loaded turn-off maxima remain unbounded; overall result is INDETERMINATE |
| A5, supplies and ownership | IRM-10-24 → TPS7A4701 15 V → TPS54202 5 V candidate; real pin map, load/thermal constraints and rail-state trace | Raw overshoot, regulator dynamics, assembly thermal behavior and physical isolated ARM/PERMIT producers remain open |
| B1, coupled circuit | Full-wave bridge, source current, shunt, boost plant, separate VD/VB, controller feedback and RevB shutdown logic | Warm precharged witness uses ideal auxiliary rail ports; no complete cold-start/rail co-simulation |
| B2, controller behavior | Nominal UCC28180 functional implementation, independent functional/current-loop/soft-start checks and intended negative controls | Not a manufacturer-qualified model; full regulation, piecewise/corner coverage and physical standby implementation remain open |

The original retained power source has54 parts and the standalone RevB
protection graph has79. Adding those counts is not an integrated circuit design.
No133-part build or component-reduction conclusion is claimed here.

## Observed switching result

The accepted witness uses120VAC at60Hz, a220 ohm load, VD/VB precharged to
389.615V and prequalified rails. F2 is an ideal switch opened at600µs. The run
ends at900µs; it is not a settled full-line-cycle operating point.

| Measured quantity | 10ns maximum timestep |
|---|---:|
| F2 opens | 599.999504µs |
| External detector asserts | 674.554552µs |
| Local latch clears | 674.602981µs |
| VD local-reservoir peak | 406.827499V |
| VB bulk-bank peak | 390.530849V |
| MOSFET VDS peak | 407.961848V |
| Gate VGS peak | 14.982053V |
| Inductor current peak | 35.684171A |

After latch clearing, the checker requires sustained driver/channel shutdown;
the final controller PWM is zero, VSENSE is0.001951V and VCOMP is0.005958V.
Repeating at5ns changes the VD peak by3.448mV and latch timing by7.248ns.
That supports numerical convergence for this model and witness. It does not
establish device margins against missing parasitics or worst-case silicon.
F2-to-detector latency and detector-to-current-cessation latency are different
quantities; these timings do not validate a universal2µs shutdown guarantee.

The separate conservative energy example assumes132VAC,50A at trip,
100/216µH inductance bounds,19.8µF and2µs delay. It gives493.950V against the
chosen500V VD screen and a3.004µs allowable-delay boundary. These assumed
inputs are not proven maxima. In particular,500V is not the450V bulk-bank
rating and the local-reservoir estimate is not a VDS/ringing bound.

## Verification

- 11 envelope unit/oracle tests pass;9 invalid CLI cases reject; an altered
 voltage screen is reflected in both the verdict and metadata.
- 15 controller functional assertions pass. Separate traces check the TI
 current-loop worked example and physical compensation-network soft-start,
 SOC discharge/recovery, standby and retry.
- The warm coupled run and its refined run pass. Disabling PCL fails with
 `PCL never latched`; bypassing external protection fails with
 `no external detector fault`. Malformed/truncated traces cannot substitute
 for either intended negative.
- 3 controller checker tests pass, including header/order, nonfinite and gap
 rejection. Accepted traces were rechecked after parser hardening.
- The supply screen validates3120 actual ngspice samples over30ms;10 Rust
 tests pass. Required witnesses include normal24V,32.4V and35V input,
 collapse/recovery,15V dropout and a75mA logic-rail load step.
- 15 existing source-graph regression tests pass. Their retained inputs did
 not change. Pinned Atopile 0.2.69 also compiled and exported the13-component regulator module; its resolved graph confirms raw VIN, regulated buck VIN, exposed-pad ground and independent NC pins. Generic passives remain unsourced.

Commands and local evidence:

```sh
cd /private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/controller-integration-06
(cd limits && rustc --edition=2021 --test envelope.rs -o /tmp/envelope06-tests && /tmp/envelope06-tests)
(cd limits && rustc --edition=2021 -O envelope.rs -o /tmp/envelope06 && /tmp/envelope06)
./controller/run_checks.sh
./supply/run_supply.sh
cargo test --manifest-path supply/rail-contract/Cargo.toml
```

Read `limits/README.md`, `controller/README.md`, `supply/README.md`,
`host/integration-contract.md` and `host/review-disposition.md` for the detailed
scope. Raw waveforms, logs, downloaded model archives, rejected approaches and
review findings are retained. TI's available controller libraries are encrypted;
the accepted model is an authored nominal implementation, not a converted TI
macro-model.

## Concrete source defect and next work

The retained current-sense diode is reverse-biased for the negative excursion
it needs to clamp, and sits before the220 ohm resistor. The reviewable
`host/isense-clamp-candidate.patch` follows TI's filtered-pin topology and names
a BAV23C silicon candidate. It remains unapplied and unqualified; changing only
the polarity of the existing Schottky could interfere with the PCL threshold.
`host/isense-clamp-diagnosis.md` records the primary references and required
VF/current/temperature checks. The accepted warm trace does not test this patch
or prove protection during inrush.

Next, apply and compile the clamp correction in a new source revision, implement
the physical standby/control interface, and establish one normal operating point
with honest cold-start and supply boundaries. Then extend to108/120/132VAC ×
low/mid/maximum permitted load before repeating faults from those states. Keep
unresolved magnetic, fuse-arc, parasitic and thermal behavior as explicit
conditional inputs. Schematic consolidation follows that evidence.
