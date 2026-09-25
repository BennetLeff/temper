# UCC28180 vendor-model availability check

## Result

TI does publish UCC28180 simulation assets. The missing item is a directly
usable, open SPICE transient model for this ngspice campaign: TI's transient
asset is a TINA-TI package with an encrypted library, and the PSpice asset is
an average model whose implementation is encrypted. The retained controller
surrogate therefore remains conditional; it must not be described as a TI
macro-model.

## Official TI sources

TI's current product page lists all three relevant resources:

- Product page: <https://www.ti.com/product/UCC28180>
- PSpice average model: `SLUM423.ZIP`, linked from that page
- TINA-TI transient SPICE model: `SLUM528.ZIP`, linked from that page
- TINA-TI transient reference design: `SLUM529.TSC`, also linked from that page

The product page labels SLUM423 as **UCC28180 PSpice Average Model** and SLUM528
as **UCC28180 TINA-TI Transient Spice Model**.  It does not claim ngspice
compatibility or provide an open-model conversion.  The same page describes
TINA-TI as the supported simulation environment for the TINA assets.

## Retained archive evidence

The exact archives already retained in
`protection/controller-integration-06/controller/sources/` are:

| asset | SHA-256 | contents relevant to this audit |
|---|---|---|
| `slum528.zip` | `9c00445c24a57c43d666c6194893d4e4f421b07733893720f9669a051a910680` | `UCC28180_TRANS.LIB`, `.TLD`, `.TSM` |
| `slum423.zip` | `a1d95663f87595b2c03acac3871c0de57f627f7af21dc38889893a46e9cecfe2` | `UCC28180_AVG.LIB`, PSpice design/archive files |

`UCC28180_TRANS.LIB` begins with `<Encrypted Library>` and its body is binary
encrypted data.  Its companion `.TLD` identifies the macro as
`UCC28180_TRANS` and includes `LOCKED`; the `.TSM` is a TINA Device Editor
binary (`Spice Macro`, TINA Device Editor 9.3.80.273 metadata).  This is a
TINA-managed model, not an open netlist that ngspice can consume.

The PSpice library has readable headers identifying `Model Type: AVERAGE`,
`Simulator: PSPICE`, `Simulator Version: 16.2.0.p001`, EVM `UCC28180EVM-573`,
and model version `Final 1.00` (dated 14APR2014).  Its subcircuits are enclosed
by `$CDNENCSTART`/`$CDNENCFINISH` blocks containing encoded payloads.  Thus the
archive is a TI-distributed PSpice average model, but its implementation is
not available as ordinary text for ngspice inspection or faithful conversion.

These observations match the retained experiment-06 model-retrieval note:
the blocker is simulator compatibility/encryption, not absence of a
manufacturer model.  No decryption, conversion, or unsupported simulator
installation was attempted.

## What this establishes for the Temper work

The model gap is narrower than “TI has no model”:

1. A vendor model exists for two intended TI tools and two different scopes:
   TINA transient and PSpice average.
2. Neither retained asset is an open, ngspice-ready transient controller
   model. The PSpice asset is average-mode and encrypted; the TINA asset is
   encrypted/TINA-native.
3. The existing `controller-integration-06/controller/ucc28180.inc` and later
   `operating-matrix-07` controller includes are host-authored nominal
   functional surrogates. They can support bounded pin/function fixtures, but
   they do not establish silicon propagation delay, hot/cold behavior, or
   full startup/regulation.

The next discriminating option is to run the official model in its supported
TINA/PSpice environment and correlate key waveforms, if that environment is
available. If the simulation must remain ngspice-only, retain the current
surrogate but label the controller behavior as authored and close the gap
with measured controller/power-stage waveforms rather than claiming a vendor
transient model.

## Reproduction of the source inspection

```sh
sha256sum protection/controller-integration-06/controller/sources/slum423.zip \
  protection/controller-integration-06/controller/sources/slum528.zip
unzip -l protection/controller-integration-06/controller/sources/slum528.zip
unzip -p protection/controller-integration-06/controller/sources/slum528.zip UCC28180_TRANS.LIB | head
unzip -p protection/controller-integration-06/controller/sources/slum423.zip \
  UCC28180_PSPICE_AVG/UCC28180_AVG.LIB | sed -n '1,45p'
```

No electrical deck, component value, or controller include was changed by
this audit.
