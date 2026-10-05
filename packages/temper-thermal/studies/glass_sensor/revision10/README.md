# R10: define the next sensor experiment

2026-10-05. Three `gpt-6-sol` agents at high reasoning worked in parallel on thermal behavior, seal/contact, and bond/leads. The main agent completed retention and integration review. No new worktree, package installation, full CAD rebuild or duplicate STEP export was created. This packet uses the existing R9 checkout and adds small source files, records and calculations only.

**The next build remains an inspectable 100/150 µm process witness, followed conditionally by a full-lead M222 article.** The new work clarifies how to measure it and why the current complete cartridge cannot yet be released.

## Decisions and findings

| Area | What advances beyond R9 | Next concrete action / boundary |
| :-- | :-- | :-- |
| Thermal | C9's island-to-bracket metal contact is open at rest and closes at capture. Its engaged heat path includes direct foot contact as well as the screw route. | Use the new conductance sensitivity to identify the interfaces to measure. It is not a new C9 response prediction; changed capacity, gap transfer and induction heating remain outside it. |
| Bond/leads | A blank build traveler now ties cure, cured gap, face disposition and electrical contact coordinates to one article and same-lot control. | Build the bare-alumina witnesses first. A live M222 experiment needs face/chemistry disposition and intact native leads. A distal Kelvin split does not remove native lead resistance up to the voltage contacts. |
| Retention | Bolt clearance can consume half the 0.20 mm nominal head-to-ring gap. Unequal contact engagement can triple mean bearing pressure relative to equal thirds. | Specify bracket locating surfaces, carrier material/process and joint preload requirements before defining torque or retention capacity. |
| Seal | A stationary sealed bulkhead with a drained wet well is a possible comparison experiment that avoids a moving membrane boundary. | This changes the ingress/cleaning architecture and has no CAD or qualification. Keep it conditional on product acceptance; it does not replace the current cartridge or solve wet contamination. |
| Contact | Downstream force/position can remain plausible during a jam. Tests now require local gap, cap reaction and thermal coupling as independent bench truth. | Challenge the proposed channels against jams, insulating films and conductive slivers. The existing unavailable firmware backend stays unavailable. |

The physical distinction matters: a probe can mechanically touch a pan through a poorly conducting film, or have electrical continuity through a tiny conductive path without useful thermal coupling. No software debounce setting can recover information that the physical channels do not observe.

## Read the evidence

- [Thermal sensitivity, assumptions and reproduction](thermal/README.md)
- [Bond/lead decision](bond-leads/decision.md), [build traveler](bond-leads/traveler.md), [blank article record](bond-leads/article-template.json), [observation columns](bond-leads/observations-template.csv)
- [Retention budgets and unresolved structural inputs](retention/decision.md)
- [Seal/contact architecture and firmware audit](seal-contact/decision.md)
- [Integration review and verification](VERIFICATION.md)
- [Content identities](source-provenance.json)
- [R9 report and existing experimental CAD](../revision9/report.html)

Manufacturer references appear next to the claims in each study. Published part or material limits are not treated as installed product qualification. The static bulkhead is a feasibility branch; the existing C9 candidate is still dry experimental CAD; the production contact backend is not selected.

## Evidence that still requires hardware or unpublished information

All physical results remain **NOT_RUN** and all supplier questions **NOT_SENT**. A 250°C seal, robust detector, bond compatibility, hot joint strength and induction/endurance performance remain unqualified. Product load, allowed ingress, supported cookware and physical shutdown-latency requirements need explicit values before a pass/fail qualification can be defined. No generic material rating or virtual sweep closes those requirements.

Current CAD pointers, firmware and R2–R9 evidence are preserved. R10 supplies preparation and conditional calculations; no production release or full C9 thermal/EM simulation is claimed.
