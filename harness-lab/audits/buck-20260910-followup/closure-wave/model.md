# Buck model feasibility (2026-09-10)

## Decision

The current `LMR51430XDDCR` model remains exploratory and cannot qualify
Stage 3. A timeboxed public-source search found no retained exact-device
vendor model bytes or independently usable export. The absence result is only
an observed retrieval result; it is not proof that TI has no private or gated
model. The blocking evidence is the missing exact model receipt, simulator
compatibility proof, and independent waveform qualification.

The device itself is a good electrical fit: TI's datasheet identifies
`LMR51430XDDCR` as 500 kHz, PFM, adjustable, with 4.5--36 V input, 0.6 V
feedback reference, and 3 A output capability. The proposed Temper envelope
(13.5--16.5 V, 3.3 V, 0.5 A continuous, optional 1 A/10 ms pulse) is inside
those ratings. This establishes feasibility of the circuit choice, not model
qualification.

## Retrieval evidence

Primary TI product page and datasheet were searched for exact and family model
assets, including PSpice, transient, SIMPLIS, WEBENCH, `LMR51430X`, and
`LMR51430XDDCR`. The product page exposed datasheet, EVM, and WEBENCH routes;
no downloadable exact model bytes were retained. The public TI E2E result
about an `LMR51430XF` transient model concerns the FPWM sibling and cannot
prove anything about XDDCR. The TI EVM guide confirms U1 is the exact
`LMR51430XDDCR` and provides a 5 V reference design, but it does not provide
the independent startup, line, and load waveform set required here.

Sources inspected:

* https://www.ti.com/product/LMR51430
* https://www.ti.com/lit/ds/symlink/lmr51430.pdf (Rev. A; exact orderable/mode at pp. 2--3, reference and ratings, operating curves)
* https://www.ti.com/lit/ug/sluuch0/sluuch0.pdf (LMR51430 EVM guide; exact U1)
* https://e2e.ti.com/support/tools/simulation-hardware-system-design-tools-group/sim-hw-system-design/f/simulation-hardware-system-design-tools-forum/1238369/pspice-for-ti-lmr51430xf-transient-model-does-not-exist-in-pspice---ti-library
* https://webench.ti.com/power-designer/switching-regulator?base_pn=LMR51430&litsection=features&origin=ODS

The live WEBENCH route was loaded with 13.5--16.5 V, 3.3 V, and exploratory
1 A maximum load. Its design view remained behind the TI Notice/Site Terms
checkbox. No terms were accepted, no generated design or model was exported,
and no vendor waveform was treated as evidence.

## Minimum trustworthy completion path

1. Host action: if permitted by the project owner, accept the WEBENCH notice
   in the browser, run nominal 0.5 A and exploratory 1 A cases separately,
   and record the selected family variant as XDDCR-equivalent 500 kHz PFM.
   Preserve the exact design/BOM, export/model bytes, displayed source and
   license, simulator/version, and settings. A WEBENCH calculation or
   schematic alone is not a SPICE model.
2. If a model download is exposed, copy the archive into a reviewable receipt
   (URL, retrieval date, SHA-256, license, model name/subcircuit, pin order,
   exact device/variant identity) and test it in the project's supported
   simulator. Retain raw logs and a minimal deck. A PSpice-only encrypted
   model is not automatically ngspice-compatible.
3. Compare model behavior against independent TI evidence and then hold out
   tests: cold startup at all three VIN corners and zero/500 mA; steady PFM
   ripple at zero, 50 mA, and 500 mA; line variation; and both 50--500 mA and
   50--1,000 mA load steps. TI datasheet/EVM plots are reference evidence,
   not a substitute for coverage of this BOM and these corners.
4. Freeze calibration separately from holdout validation. Only after exact
   identity, license/source, simulator replay, and external correlation are
   reviewed should a non-synthetic model receipt be added to the approval
   registry. Until then leave Stage 3 and the model registry blocked.

## Viable redesign candidates (research only; no BOM change)

These are alternatives to investigate if exact XDDCR model access remains
blocked. They are not selector recommendations and still require pinout,
layout, thermal, availability, and full redesign review.

### LMR36510A (first candidate)

TI publicly lists an **unencrypted PSpice transient model**, `SNVMBX9A.ZIP`,
on the LMR36510 product page. The Rev. B datasheet specifies 4.2--65 V input,
1 A synchronous buck, adjustable output, and automatic PWM/PFM behavior; its
3.3 V typical application uses 400 kHz and a 1 A load, and it explicitly shows
0.5--1 A load-transient curves. Thus 13.5--16.5 V, 3.3 V, 0.5 A continuous,
and a 1 A pulse fit the electrical envelope. It is an 8-pin PowerPAD DDA
device, so this is a material footprint/BOM/thermal redesign.

Sources: https://www.ti.com/product/LMR36510 and
https://www.ti.com/lit/ds/symlink/lmr36510.pdf (Rev. B, pp. 4, 9, 16,
21--24). Exact archive bytes, license text, and ngspice replay have not been
retrieved here.

### LMR33630A (second candidate)

TI publicly lists encrypted and unencrypted PSpice transient models,
including `SNVMBF9A.ZIP`, on the LMR33630 product page. The family is a 3.8--36
V, 3 A synchronous buck; the A variant is documented with a 400 kHz EVM and
the product page supplies the model archive. This covers the input, output,
and load envelope, but it is a 400 kHz variant and has different package /
pinout options (DDA or RNX), so it needs a new power-stage design and explicit
PFM/FPWM-mode selection review. Exact archive bytes, license text, and
ngspice replay have not been retrieved here.

Sources: https://www.ti.com/product/LMR33630 and
https://www.ti.com/lit/ds/symlink/lmr33630.pdf.

## Limits and host handoff

No TI terms were accepted, no vendor was contacted, no hardware was ordered,
and no selector/BOM was changed. The host should perform the browser-only
terms decision and any gated export, then retain the receipt and raw files as
described above. Public search results show model availability for the two
redesign candidates, but model identity, license, archive integrity, and
simulator compatibility remain unverified until their archives are actually
retrieved and replayed.
