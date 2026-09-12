# Assigned pins, physical pads and connected copper are separate claims

Require all three layers before accepting a board:

1. An independently reviewed source contract fixes physical package pins, part identity and topology. Schematic/PCB parity alone can reproduce a wrong circuit.
2. Native document binding checks every actual physical pad and UUID. A relay may have four logical pins and six physical solder pads. Mechanical NPTH holes are a separate census. Reject missing, duplicate or conflicting physical identities without rejecting valid repeated pin numbers.
3. Native copper clusters must form the full expected source-net partition. The power-entry checkpoint has correct assigned pin nets but 94 unrouted links. Its source graph passes and its Rust copper-connectivity rule fails. Do not label this construction complete.

Use KiCad to load and place the selected library footprint before routing. The source skeleton can preserve pad centres while corrupting pad-body angles or omitting required metadata. The initializer now compares native pad-body orientation at the actual pose. A separate refresh test uses asymmetric 45-degree placement, repeated relay pads and a mechanical hole. Never substitute an implementation self-roundtrip for that external oracle.

Validate actual output content and the artifact it refers to. Native ERC findings are nested under sheets; DRC command exit zero is not an acceptance result. Copy the candidate's complete library/project context when promoting it. Standalone footprint files with Lisp-style semicolon comments failed native loading even though the text skeleton appeared usable.

The PFC investigation also required defining watts at the boundary: the product target is nominal 1,800 W AC input, not 1,800 W DC bus output. The corrected doubler model failed RMS/ripple constraints. Exact inductor current alone was insufficient: the rejected laminated part was specified only to 20 kHz. Numerical circuit values and chosen topology are board-specific evidence, not portable defaults.

Evidence is the gate-drive09 and power-entry05 checkpoints plus the registered Rust and native oracle tests. The notes were reviewed after construction. Their existence does not prove a controlled agent-memory improvement; initial preparation receipts likewise do not prove delivery through the conversation provider.
