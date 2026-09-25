# Power-entry component and interface selection review

2026-09-22. Three bounded Luna research tasks completed against the unchanged
136-instance `interface-defaults-11` candidate. The parent checked their claims
against current source and primary datasheets, corrected two selection errors,
and rejected an overvoltage-divider proposal with executable arithmetic.

This round produces a shortlist and acceptance cases. It does not select a
complete qualified interface, implement a new circuit, or change the part count.

| Work unit | Result | Remaining decisive work |
|---|---|---|
| [Command isolation](commands.md) | ISO7740FDWR is a concrete evaluation candidate; use separate SELV 3.3 V and HOT 5 V domains | Define and test low-before-arm behavior across rail return and wire reconnection; isolation alone does not supply that behavior |
| [AUX supply protection](supplies.md) | Reuse the existing HOT supply candidate as a starting point; evaluate a cutoff after its 15 V regulator | Bound downstream peak voltage and recovery; reject the suggested 17.5 V cutoff setting |
| [Current-sense clamp](clamp.md) | Retain BAV23C provisionally; no supported substitution or deletion found | Obtain applicable low-current/temperature bounds and a justified sensing-error allowance |

## Parent corrections

1. **An upstream cutoff is not protection against a downstream regulator fault.**
   Luna initially placed a roughly 29 V cutoff before the 15 V LDO. A failed
   LDO can pass a normal 24 V input to the driver without triggering that cutoff.
   The corrected evaluation placement is after the LDO, before AUX consumers.
2. **A nominal 17.5 V cutoff is too close to the 18 V requirement.** The proposed
   137 kΩ/10 kΩ divider reaches 18.0075 V at the specified OVP threshold maximum
   even with exact resistors, and 18.346540 V with ±1% resistor variation.
   [Rust screen](ovp-screen.rs), [results](ovp-screen.csv). These calculations
   reject the suggestion before considering dynamic overshoot.
3. **The HOT input contract does not apply unchanged to the SELV side of an
   isolator.** Luna's initial handback unnecessarily required a new SELV 5 V
   rail. The shortlisted isolator supports level translation; SELV 3.3 V inputs
   and HOT 5 V outputs have different voltage contracts. Actual drive margins
   and power-off behavior still need checking.

The parent owns these conclusions. Worker handbacks are research inputs, not
component acceptance. [review-receipt.json](review-receipt.json) records the
accepted and corrected findings; [dispatch.json](dispatch.json) records scopes.

## Integrated acceptance cases to implement next

| Case | Required observation | Current status |
|---|---|---|
| Valid cold start | Both rails valid; ARM remains low through qualification; only a deliberate subsequent edge starts RUN | Revision 11 has nominal local tests; new producer/crossing not modeled |
| SELV reset or loss | PERMIT withdraws; receiver inputs have defined levels without back-powering | Isolator/producer-specific test not run |
| HOT rail loss/return with SELV ARM high | Supply return cannot manufacture an accepted start command | Known unresolved interface behavior; cannot assume default-low isolation fixes it |
| Individual ARM reconnect while source is high | Either prevent an accepted restart or explicitly reject this interface architecture for the required fault scope | Revision 11 retains a counterexample |
| Regulator pass-through and source OV | Actual driver supply remains within its required envelope, including disconnect delay and charge transfer | Cutoff placement identified; physical transient bound absent |
| Supply cutoff recovery/hiccup | Rail recovery alone cannot rearm or repeatedly energize the power stage | Supply and command recovery must be designed together |
| Current-sense surge/PCL operation | Clamp limits negative ISENSE excursion without invalidating current sensing over the applicable range | Missing component/application bounds |

The next bounded implementation should combine the command crossing and its
restart qualification in an isolated source/fixture. Merely adding an isolator
would leave the known restart issue unresolved. In parallel, develop the
downstream cutoff's complete static and transient budget using actual load and
capacitance limits. Fuse coordination and complete-converter/PCB work remain
separate unfinished items from the earlier handoff.

## Evidence and limits

All workers were read-only and were interrupted after handback. Parent writes
are confined to this directory. No existing circuit, PCB or frozen result was
changed; no vendor message, purchase, commit or push occurred. No new circuit
simulation was run. The only new executable result is the standalone Rust
divider screen, compiled without touching the shared Cargo/pyo3 cache.

`input-identity.json` binds nine source/contract/document files and the base
commit; `input-verification.json` confirms their preservation. The worker
model requested was `gpt-5.6-luna`; served-model identity was not independently
attested. Primary datasheets were read through the web tool. A shell PDF
download failed DNS resolution and was not used as evidence.
