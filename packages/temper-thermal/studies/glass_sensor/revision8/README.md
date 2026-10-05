# R8: what to resolve before the first cartridge build

**The next milestone is process and fixture feasibility, followed by a dry, off-induction thermal comparison.** The three R7 numerical controls remain useful, but public evidence does not yet support treating their bond, formed leads or seal envelopes as fabrication instructions. All physical results remain **NOT_RUN**. R8 is a readiness review; the current CAD stays at R7.

Open [the readiness report](report.html), [bond/lead evidence and traveler](bond-leads.md), [seal/contact decision](seal-contact.md), [retention/induction review](retention-induction.md), and [the staged build packet](FIRST_BUILD.md).

## What this review changes

1. **Bond processing needs resolution before fabrication.** Both R7 nominal layers (75 and 100 µm) are thinner than Cotronics' generic published bond guidance. Its ceramic instructions and FAQ give different recommended ranges; neither is a lot-specific Resbond 908 approval. A generic maximum-properties post-cure also exceeds the IST308 operating range. Obtain the exact process rather than selecting a thicker layer or cure schedule by inference. See the [primary-source audit](bond-leads.md).
2. **The lead arrangement is an integration hypothesis.** M222 has platinum-clad nickel leads; IST uses the stated gold-coated nickel family. Their electrical resistance reference datums differ. The IST near-element forming warning needs disposition for the sub-millimetre R7 installed route. Installed calibration and a sensor-compatible bond/join process remain required.
3. **Historical retention numbers do not describe the current bearing geometry.** R4 used a 0.30 mm toe lever. The R7-inherited geometry gives about 0.45 mm for a uniform pressure distribution across the overlap, with load-location uncertainty. The same straight-beam approximation therefore changes; no strength pass transfers. Required product loads, weld/bend concentration and ceramic capture strength remain unresolved.
4. **A high-temperature material name does not select the moving seal.** The complete boundary must include both motion stages, feedthroughs, pressure reference and drainage. The proposed 10 mN parasitic budget already allocates 3 mN pressure, 3 mN hysteresis and 4 mN harness/witness force, leaving no additional elastic margin at all three maxima.
5. **The software interface does not supply contact ground truth.** Existing interlock and synthetic fault work can check logic. A jammed mechanism or insulating load-bearing debris can still produce plausible signals. A production observable and demonstrated end-to-end inhibition remain separate gates.

## Why contact and heat leakage are the next thermal measurements

The R7 uniform-contact nominal predictions are 2.91 s / 2.474°C for the M222 control, 2.78 s / 2.441°C for the thin M222, and 2.05 s / 2.577°C for IST308. These are pan-step t90 and thermal underread at 200°C under the declared R7 boundary conditions, not complete-system accuracy.

Even the lowest steady underread among the 54 R7 contact/loss cases is 1.407819°C (thin M222, assumed uniform contact with href=4000 W/m²K). With the **proposed**, unmeasured 1°C nonthermal reserve retained from R5, that is approximately 2.408°C for the planning sum, so none of these cases demonstrates the joint system objective. That sum is an allocation exercise, not a measured uncertainty budget. A future calibrated correction needs independent holdout evidence and cannot silently improve a raw-sensor claim.

Measure force/contact sensitivity and body/anchor-temperature sensitivity independently. Then decide whether process changes, reduced leakage or a different package address the actual measured limitation. Refit only on declared fit data and keep whole-pan holdouts untouched. The mathematical R7 results have not changed in R8.

## Work packages and exit evidence

| Work package | Concrete next deliverable | Exit evidence / responsible role | Current status |
| :-- | :-- | :-- | :-- |
| Bond and lead process | Exact lot-specific adhesive instructions; sensor bondable face, trim/form/join disposition; controlled traveler | Manufacturer evidence and manufacturing review resolve the identified conflicts; witness sections and stability measurements then test it | Public evidence reviewed; supplier answers and specimens OPEN |
| Dry metrology fixture | Received-instrument mounting, guides, clamp hardware, optical access and in-situ uncertainty budget | Mechanical/metrology lead demonstrates the required force/displacement capability and no fixture-created pan constraint | Nominal STEP fit only; instruments/fixture build OPEN |
| Thermal comparison | Matched M222 control/thin pair, then complete IST article after process gates; predeclared pan split | Independently referenced error/response with measured geometry, force, boundaries and uncertainties; then held-out pans | Acquisition preparation available; NOT_RUN |
| Seal architecture | Full boundary and both-stage force diagram; supplier pressure/stroke/temperature/cycle requirement packet | Candidate-specific hot cyclic force/pressure/leak evidence fits the complete budget; no double counting | No qualified installed candidate |
| Contact inhibition | Observable architecture and adversarial equivalence tests linked to the existing interface | Independent gap/contact ground truth plus output-disable trace under declared faults and latency requirement | Production observable and measured latency OPEN |
| Retention | Current geometry/load-location screen and valid cap-only/housing fixture drawings | Product-derived loads and lifetime limits, material/process evidence, actual-load-path tests, then after-stress checks | Historical screen applicability corrected; physical acceptance OPEN |
| Induction/endurance | Matched dummy/real/field-off acquisition, probe-perturbation controls and traceable exposure schedule | Qualified lab separates pickup, physical cap heating and pan hotspots; repeats calibration/contact/retention/leak checks after stress | Prepared protocol; NOT_RUN |

## Decisions that must precede physical acceptance

The product/mechanical/electrical owners must define cookware coverage, maximum temperature including overshoot and duty, handling/pull/side loads, allowable permanent set, service/cleaning exposure, leak paths and limits, and maximum fault-to-power-off latency. Historical 1 N/2 N screens, proposed counts and material datasheet ratings do not supply those requirements. The old under-glass mount's load/travel/life targets do not apply to this in-glass design.

The next useful supplier discussions are already drafted in the three workstream documents. **They have not been sent.** The next useful hardware work is the staged [first-build sequence](FIRST_BUILD.md); no hardware has been purchased or operated here.

## Evidence preservation

R7 commit: `fd618613c`; its source/artifact manifest, results and current CAD pointers remain unchanged. R8's manifest records this packet and the exact inherited evidence it summarizes. Manufacturer URLs and document sections are recorded in the workstream documents. The local verification checks identity and arithmetic consistency; they are not physical qualification.
