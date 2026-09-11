# Exact-device model qualification follow-up

Status: blocked; no new simulation or model approval is claimed. This is the
host's follow-up alongside three Luna work units, based on the current
`LMR51430XDDCR` circuit at `a75ca538d87d6578917d0cb3a50da7f14ebdc210`.

## Public reference evidence

The [current TI product page](https://www.ti.com/product/LMR51430) exposes a
datasheet, EVM, and WEBENCH route; no downloadable exact-device SPICE archive
was obtained from that page. The historical
[TI support answer](https://e2e.ti.com/support/tools/simulation-hardware-system-design-tools-group/sim-hw-system-design/f/simulation-hardware-system-design-tools-forum/1238369/pspice-for-ti-lmr51430xf-transient-model-does-not-exist-in-pspice---ti-library)
points to published device-page models, but concerns the XF variant and is
not proof that an XDDCR model does not exist elsewhere today.

The [TI EVM guide](https://www.ti.com/lit/ug/sluuch0/sluuch0.pdf), SLUUCH0,
April 2022, identifies U1 as LMR51430XDDCR and uses the same exact output
capacitor MPN as Temper, GRM32ER71E226KE15L, specifying 22 uF/25 V/+/-10%.
Its reference is 5 V with a different inductor, input network and four-layer
board. The guide contains setup, layout, schematic and BOM information, but
does not supply the required independent startup/line/load waveform set.
It strengthens component and exact-device reference identity, not dynamic
qualification of the Temper circuit. A retained copy is under `sources/`.

## Live WEBENCH attempt

The host opened the official
[LMR51430 WEBENCH entry](https://webench.ti.com/power-designer/switching-regulator?base_pn=LMR51430&litsection=features&origin=ODS)
in a fresh browser tab. The visible form loaded. It was populated with
LMR51430, 13.5–16.5 V input, 3.3 V output, 1 A maximum output and 70°C maximum
ambient to explore the proposed stress envelope. This is an exploratory input;
it is not a validated device selection or a continuous 1 A product requirement.

The View Designs button remained disabled behind the required WEBENCH Notice /
TI Site Terms acceptance checkbox. Acceptance was not performed. An explicit
terms-acceptance choice was requested from the user; none was available when
this record was written. No design, exact XDDCR/PFM selection, waveform export,
model bytes, model license or simulator compatibility was verified from the
live tool. The blocker is an observed terms gate, not a missing browser.

## Concrete completion path

After the terms choice, try the current circuit's nominal 0.5 A design and
the proposed 1 A stress case separately. Verify that the selected device is
XDDCR, 500 kHz PFM, with 0.6 V reference; do not accept XF/FPWM or a substituted
part. Record exactly which components the tool changes and distinguish its
generated design from the current nine-component BOM.

If the tool provides usable simulation/export, retain the exact device/mode,
BOM, model/deck bytes if available, source/license, simulator/version/settings,
and raw supported outputs. WEBENCH calculations or a schematic export alone
do not imply an ngspice-compatible model. A vendor-hosted simulation without
exported model bytes may require a separately designed evidence adapter; the
current ngspice gate cannot silently accept it.

Independently qualify startup, input variation and both proposed load profiles
against device evidence that covers their conditions and outputs. Freeze any
calibration set separately from holdout validation. The existing datasheet-
derived model may be refined, but its own waveforms cannot validate its
unpublished compensation, PFM behavior, transient response or losses.

If no adequate vendor/reference evidence is obtained, the remaining action is
a vendor request or future exact-device bench correlation. No support message,
hardware order or powered test has been performed. Keep the model registry
empty and stage 3 blocked until a real reviewed receipt supports the mandatory
claims. Public-page research has not exhausted private vendor support.
