# R9 final independent review

Reviewed the root README/report/verification, process decision, thermal adapter and runner, inherited pinned R5/R6/R7 thermal sources, baseline mechanical scripts and their recorded outputs. Read-only source and artifact review; no physics or CAD rerun was performed. All physical work remains **NOT_RUN**.

## Completed baseline scope

**No new blocking defect found.** The prior source-copy/receipt finding is resolved: inherited compiler inputs are copied into isolated snapshots, the copies are checked against the pins, and compilation uses those copies. The local unit snapshot is verified against its captured hashes, and the success receipt uses that same captured hash list. The deterministic corrupt-snapshot probe exercises the formerly unverified boundary. The four recorded failure probes remove the seeded success receipt and produce no new physics CSV.

Independent read-only checks matched every thermal receipt hash to the supplied files and inherited inputs; confirmed 168 scenario rows with parametric/unapproved and NOT_RUN labels; checked rounded boundary contributions against total underread; and confirmed the recorded test result is 47 passed, zero failed. These verify the supplied run record, not an independent execution. The old 46-test/144-case/three-probe review is a historical checkpoint.

Tracing `r9_process_plant → r7_candidate → candidate → build` confirms that equivalent thickness changes the intended two half-bond resistance terms and intermediate bond capacity. Restoring actual bond volume removes the equivalent-thickness capacity artifact. Other package/contact/cover/native-lead parameters remain inherited. The fixed 2 MJ/m³K capacity is a proxy, explicitly not a 569 property. The existing reference-matrix test and analytical resistance test support these claims. A future whole-matrix isolation test at non-reference conductivity for both package families would make the contract easier to maintain; no current unintended term change was found.

Mechanical result checks confirmed 21 sampled states, no reported collision/check failures, three detected overtravel controls, six complete endpoint exports, two open-witness exports, matching hashes for all eight STEP files, and nine explicitly open upward finger attachments. The scripts validate reimported solids and measure actual reimported contact faces. Directional seating contact cannot transmit the required upward finger reaction; the report correctly retains that missing attachment as a finding despite successful nominal catch checks. These are sampled axial geometry checks, not strength, continuous motion, hot tolerance, assembly qualification or physical retention evidence.

The root conclusions stay within these limits: no named-569 response, no transfer of R7 thermal scores to the open bare-alumina witness, and no complete-system target pass. Published-process selections remain conditional on received instructions, compatibility and measured installed behavior. This review checked that claim separation and internal consistency; it did not re-audit the external manufacturer publications.

## Final packaging check

Retain `review.md` as a clearly identified checkpoint and link this final disposition so its obsolete counts and unresolved-race wording are not mistaken for current status. The root content manifest and any separate bolted candidate were still being finalized at this checkpoint and are outside the baseline findings above.

## Separate C9 bolted-candidate addendum

Reviewed `bolted_candidate.py`, `fastener_access.py` and their recorded JSON results after candidate completion. **No new blocking defect found within the stated nominal-geometry scope.** Independently matched the three candidate STEP hashes and checked the three poses have no unexpected intersections or missing modeled electrical joins. Candidate parts use the baseline collision census without new exemptions for bracket, screw, nut or carrier collisions. The actual reimported bearing faces are checked against expected areas, rather than accepting only pre-export geometry.

The separate candidate defines an ideal positive path from island to bracket, screw head, nominal matching screw/nut thread connection and nut bearing against the carrier. Helical thread flanks, thread fit, preload and locking are not modeled. That distinction is necessary: this is a specified nominal fastener connection, not simulated thread retention or a qualified hot joint. The baseline nine finger seats remain open upward joints; this candidate does not retroactively change that finding.

The supplied result contains 18 individual bracket insertion samples, six housing-lowering samples, and the deliberately inadequate shallow passage produces 0.615371745 mm³ interference. Bracket insertion excludes **all** C9 components, so those samples demonstrate each bracket against inherited internals before fastening, not a complete sequence with previously installed brackets/fasteners. They are discrete samples, not swept-volume proof. The final three poses do include all candidate components. Nine separate fastener/access checks use screw-approach and rotating-nut envelopes plus a minimum hex-key shaft with the housing/glass/seals absent; these do not establish wrench/driver-handle access, torque stroke or operator access.

The wider foot, holes/passages and metal brackets require their own material/process, hot-load, tolerance, thermal and electromagnetic evidence. R7 numerical response and insulation behavior cannot be inherited. Keep the candidate marked experimental and physical NOT_RUN. Candidate supplier dimensions and external product literature were not independently re-audited in this bounded source review; the final separate candidate receipt/documentation was still being packaged.

## Final integration disposition (main agent)

The insertion omission identified above is addressed by the supplemental `fastener_access.py` checks and `fastener-access-checks.json`. The main agent inspected the source and all 18 recorded bracket positions: each includes the other two brackets and their four installed fasteners, omitting only the moving bracket and its own not-yet-installed screw/nut from the counterpart set. All 18 report no intersections above the unchanged 1e-6 mm³ threshold. This supplements the original individual insertion checks; it remains discrete geometry sampling, not continuous swept-volume or tool/torque qualification. This disposition is the main agent's review, not an additional independent-agent rerun.
