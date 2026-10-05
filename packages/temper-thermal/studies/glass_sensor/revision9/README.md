# R9: resolve the next experimental design

**Use a 100 µm open Ceramabond 569 material witness first, with a 150 µm comparison. Preserve full native leads for the later open RTD article. Keep R7 as a numerical reference, not a released fabrication recipe.** This closes a process-selection decision without pretending that public product literature qualifies a finished sensor.

The [report](report.html) summarizes new results. Detailed evidence is in [process decisions](process-decision.md), [mechanical checks and witness CAD](mechanical-resolution.md), and [the thermal adapter/results](thermal/README.md).

## Decisions made

| Open question | R9 resolution | What this does not establish |
| :-- | :-- | :-- |
| Must Resbond 908 receive a >300°C cure? | The exact product sheet assigns that full-cure instruction to 903HP. No mandatory >300°C 908-specific cure was found. | Received-lot 908 thin-layer process and sensor compatibility remain unknown. |
| Which process should be tried next? | Standard Ceramabond 569, on an accessible 316L/bare-alumina witness at 100/150 µm, is a better-supported candidate from published gap/cure guidance. | Not a selected production adhesive, complete hot/wet insulator or named-material thermal prediction. |
| Should the first article push to 75 µm? | No. In the existing M222 model, 100→75 µm buys only 0.13 s and 0.034°C. Establish the process at 100 µm before aggressive thinning. | A new material may have different k/capacity; those data remain necessary. |
| How to avoid the unapproved near-body lead operation? | Use an open process-isolation article with the complete delivered leads and remote connections. Defer the enclosed short-stub route. | The open RTD article requires a permitted bond face/process; it does not inherit R7 response or fit. |
| Do the nominal catch surfaces exist? | Yes, but the audit also finds that the separate upper fingers have no modeled attachment carrying upward load into the carrier. Their seated face cannot close that load path. | The separate bolted candidate supplies a nominal attachment/assembly route; actual thread/preload, hot strength, tolerance and life remain unqualified. |
| Can a high-temperature compound close the seal problem? | No. Keep the prototype dry and use a separate seal cell; no reviewed installed candidate has a complete hot cyclic force/boundary qualification. | No sealed-cooking authorization or production contact backend. |
| Can another algorithm establish jam-resistant contact? | Existing software stays fail-closed. Qualification needs a physical observable tested against independent gap/force and insulating-debris ground truth. | Synthetic channel agreement or host tests do not prove physical contact. |

## A separate positive-attachment candidate

The baseline audit exposed a real missing interface: the ceramic catch fingers only sit on the carrier. **C9-BOLTED-M222-control** replaces them with three discrete 316L catch brackets and matching nominal M1.6 through-bolts/nuts. The carrier receives foot and upright passages so the brackets can slide into place after the island, before the housing. The screw axis moves to radius 7.1 mm to clear the upright ring. This is separate experimental CAD; it does not modify R7.

The candidate passes three complete nominal poses, three STEP reimports, 18 individual bracket insertion samples and six housing-lowering samples. A further 18 insertion checks include the other two installed brackets and their fasteners; nine minimum fastener/key-shaft access checks also pass. The shallow foot-only slot is retained as a failing counterexample, which justifies the upright passage. The model now represents a positive bolted attachment; thread engagement is an ideal matching-thread interface, not a helical contact/strength simulation. Preload, torque, locking, carrier material, bearing strength, complete tool access and hot life remain unqualified.

See [the mechanical resolution](mechanical-resolution.md) and [bolted candidate details](mechanical/bolted-candidate.md) for exact fastener references. Added metal and altered carrier geometry require a new thermal/induction assessment: none of the R7 or R9 thermal tables predicts this candidate's performance.

## What the new simulation resolves

The pinned Rust network was exercised over **168 process/contact cases**. At inherited bond k, M222 nominal uniform-contact response is 2.91 s at 100 µm, 3.16 s at 150 µm and 3.68 s at 254 µm. These quantify the cost of candidate process thicknesses; they are not approved cartridge geometries.

At 100 µm, the hypothetical k range 0.5–4 W/mK moves M222 response from 4.09 to 2.73 s. A low-temperature cure is therefore insufficient grounds to assign a thermal score to a replacement adhesive. The assumed volumetric heat capacity stays fixed at 2 MJ/m³K and is explicitly not a 569 property.

The nominal M222 underread decomposes into 2.263°C from the model's body boundary and 0.211°C from its glass boundary. This supports a separate body-temperature sensitivity experiment; it does not identify one physical leakage path. Even the best virtual case plus the inherited proposed 1°C nonthermal reserve remains above the 2°C planning target. No complete-system target was demonstrated.

## The smallest next physical activity

1. Confirm the received standard-569 instructions and acquire identified bare-alumina/316L witnesses. Use the open CAD and external gap control; no permanent spacers enter the bond.
2. Record actual cure and subsequent dry-hot dimensional/electrical changes. Section and measure the bond; retain failed or inconclusive specimens. A single section can falsify a process, not prove repeatability.
3. After exact bond-face/compatibility disposition, repeat with M222 and full native leads, recording electrical contact coordinates and untreated same-lot controls.
4. Only then design an enclosed successor using the observed process, permitted lead route and measured material/thermal behavior. Re-export and rerun that configuration; do not reuse R7 labels.

All hardware remains **NOT_RUN**. This work does not send supplier questions, purchase parts or operate hardware. The exact remaining supplier questions are narrowed to five recipient-specific rows in [the process decision](process-decision.md); additional web searches cannot supply received-lot or unpublished compatibility facts.

## Evidence and preservation

The base commit is `c4f66c38d` (R8). R5–R8 artifacts and current-R7 CAD pointers remain unchanged. R9 adds experimental checks, witnesses, a parametric thermal adapter, source interpretations and a report. It is **not a production release**. See [verification](VERIFICATION.md), [final independent review](final-review.md) and [content identities](source-provenance.json).
