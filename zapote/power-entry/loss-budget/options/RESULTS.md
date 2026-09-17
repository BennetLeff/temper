# PFC assurance and three electrical options

Update: [experiment 01](experiment-01/RESULTS.md) now compares all three
MOSFETs through the maintained switching model. C7 has the lowest conditional
nominal partial loss, but device sensitivity ranges overlap and physical
qualification remains INDETERMINATE. The next step is a source-bound gate-drive
comparison, not automatic substitution.

The four Luna work packages are integrated together so numerical safeguards
and component research use the same comparison contract. The current PCB and
its STW65N65DM2AG remain unchanged. No option is qualified or selected.

## What to do with each option

| Option | Result | Next discriminating work |
| --- | --- | --- |
| [Existing MOSFET and drive](existing-drive/REPORT.md) | The external 15 V supply does not establish the actual gate-high voltage or plateau current. The 136 W nominal result remains a conditional sensitivity. | Establish the auxiliary supply contract and applicable driver I–V/gate waveform; compare split turn-on/off resistance against the authored 10 Ω network. |
| [Replacement MOSFET](replacement-fet/REPORT.md) | IPW65R045C7 is the first modeling candidate; IPW65R041CFD7 is the alternative. Lower typical Miller charge is promising, but source conditions differ. | Feed exact source-bound candidate parameters into the maintained switching model, with the same operating cases and explicit driver uncertainty. Do not infer total loss from Qgd alone. |
| [Replacement MOSFET plus driver](replacement-pair/REPORT.md) | IMZA65R048M1H + UCC27624DR needs regulated 18 V and Kelvin routing. NTH4L060N065SC1 + UCC27524AD is a proposed 15 V screen, not a manufacturer-recommended turn-on claim. | Resolve bias, enable/UVLO sequencing, gate overshoot and source curves before modifying CAD. Obtain comparable switching evidence at instantaneous event currents and temperature. |

The second option is the smallest electrical experiment. It is a priority for
the next model, not an approved substitution. Pair A's exact Infineon PDF bytes
remain uncaptured; indexed distributor inventory is indicative, not a live
procurement guarantee. Read each candidate record for its individual gaps.

The partial arithmetic cannot rank complete assemblies. Conduction uses
duty-weighted switch RMS; switching uses event currents. Different temperature,
gate-voltage and current test points remain different conditions. Datasheet
Eon/Eoff may already include capacitive energy, so adding Eoss indiscriminately
would count it twice. No predicted savings or new heatsink size is claimed.

## Harness boundary

The new Rust assurance adapter emits three separate findings: numerical
verification, physical applicability and hardware qualification. The analytical
reference and scenario bindings can pass while the latter two stay
INDETERMINATE. Assumptions cannot promote this sensitivity model to acceptance.
These rules are required by the common power-entry runner, not only by tests.

Mutation coverage targets missing or stale provenance, reference disagreement,
non-finite results, wrong waveform moments, scenario-label drift, duplicate or
omitted losses, and fabricated measured-evidence labels. A retained PDF must also
have a PDF header as well as the expected digest; that check does not establish
the correctness of its contents or applicability.

This is bounded assurance of this model and adapter. It cannot prevent every
future modeling error. Numerical convergence, agreement between our own
functions, and a well-formed hash are each insufficient physical evidence.

## Review and verification

The independent Luna review receipts and their dispositions are retained under
`verification/`. The coordinator reproduces the option arithmetic, checks source
file types and hashes, and tests the integrated Rust workspace and common runner.
See `verification/VALIDATION.md` for the actual commands and outcomes; worker
claims and sparse-checkout test limitations are recorded separately.

Repository learning notes link these failures to executable protections. The
delegation record captures requested model, ownership and context hashes; it is
not proof of complete prompt delivery or a new frozen memory-catalog revision.
