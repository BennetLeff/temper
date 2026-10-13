# BOM strategy claim and criterion map

This map relates the [strategy](../bom-benchmark-optimization-strategy-2026-10-13.md) to the [literature review](README.md). L01–L13 identify source entries there. “Method support” means the source supports a way of evaluating a decision; it does not validate Temper or this rubric.

## Main claims

| Claim | Evidence | Disposition |
|---|---|---|
| Required function should guide cost reduction | L01 | Supported method; electronics translation is our application |
| Purchase price alone is an incomplete comparison | L03 abstract, L04 summary | Supported framing; exact cost terms require Temper data |
| Fewer unique parts generally means a cheaper build | L05 abstract; L06 model; L07 case | Reject as a general rule; retain only a tested hypothesis |
| Fewer placements guarantees lower cost or better yield | L02 process method; L07 case | Reject guarantee; require process and failure evidence |
| All costs can be represented by a generic complexity penalty | L04 summary; L06 context-specific costing | Reject; separate avoidable cost, allocation and capacity benefit |
| Minimum mechanical part count can decide circuit-part deletion | L02 theoretical criteria | Reject transfer; electrical functions and fault behavior control |
| A nominal or package match establishes an alternate | L08 abstract; L09; existing technical rubrics | Insufficient; qualify against application requirements |
| More distributors automatically creates independent supply | L11 abstract model | Not established; upstream-dependence evaluation is our extension |
| Future substitution/redesign work belongs in the economic case | L10 | Supported method; support horizon must fit Temper |
| Basic catalogue classification always minimizes assembly cost | L12, dated official fee structure | Reject; compare actual Economic/Standard route and complete order |
| Freeze a corrected digital board/BOM with hashes | User workflow and project identity rules | Retain as our comparison-control protocol |
| Every adopted board must be cheaper/simpler and technically better | User preference | Retain as project objective; not a universal literature criterion |
| Supplier outreach should always follow all digital optimization | User sequencing preference; L02 early process reasoning | Qualify: broad outreach can wait, decisive feasibility facts may not |
| Our 20 ordinal scores predict BOM quality or savings | No validation study | Reject; use them for traceability and evidence follow-up only |

## All 20 BOM criteria

| Criterion | Basis | Boundary of support |
|---|---|---|
| BOM-01 exact part/design identity | L08/L09; existing BP-03 | The exact field schema and hash protocol are project controls |
| BOM-02 completeness/accessories | L03 framing; existing BP-07/22 and BOM workflow | Specific accessory reconciliation and counting are our engineering procedure |
| BOM-03 role requirements | L01/L13 | Method support; Temper supplies actual acceptance criteria |
| BOM-04 voltage/transients | Existing BP-03/04 and AOE technical rubric; L08 method | No new rating or stress threshold was established here |
| BOM-05 current/pulse/interruption | Existing AOE power/fault rubric; L08 method | Installed fault and selected-part evidence still required |
| BOM-06 thermal/lifetime | Existing AOE-14 and MAG-09; L08/L10 method | Cost literature does not determine thermal limits |
| BOM-07 effective capacitor behavior | Existing BP-04, AOE-02 and SI/PI rubric | Exact component and mounted behavior remain candidate evidence |
| BOM-08 magnetics | Existing MAG-05–12; L08 method | Bias/loss/insulation thresholds are not supplied by cost models |
| BOM-09 sensing/protection accuracy | Existing AOE-16–20 | Budget and tests must be tied to the selected design |
| BOM-10 approvals/insulation | Existing BP-28, AOE-24 and MAG-11 | Application-specific requirements remain outside this literature corpus |
| BOM-11 fit/interchangeability | Existing BP-06/07 and AOE-35; L09 method | Drawings, mating system and assembly fit still require verification |
| BOM-12 dynamic behavior/sequencing | Existing AOE/SI/PI rubric; L08 method | Footprint or catalogue equivalence cannot establish circuit equivalence |
| BOM-13 actual build simplification | L02/L12 | Measure relevant operations; no guaranteed defect/yield improvement |
| BOM-14 comparable price basis | L03 framing/L12; our costing protocol | No Temper quote or fresh component price survey exists in this review |
| BOM-15 installed-cost improvement | L03/L04/L07 | Cost drivers and boundaries must be specified; no savings demonstrated |
| BOM-16 supply arrangement | L08/L10/L11 | No ready-made single/dual-source policy for this product |
| BOM-17 valid consolidation | L05/L06/L07 plus technical rubrics | Commonality is conditional; demand/compatibility assumptions matter |
| BOM-18 inventory and change costs | L03/L10; our accounting extensions | Residual-stock, scrap and cash treatment must avoid double counting |
| BOM-19 reproducible controlled change | L09 method; project generation/identity rules | Atopile ownership and export regeneration are Temper-specific |
| BOM-20 demonstrated gain | L13 method; project comparison protocol | The ordinal scoring system and confidence rules are our synthesis |

The procurement/substitution/redesign classification is our organizing scheme. It is consistent with distinct purchasing, part-assessment and lifecycle decisions in the sources, but it is not attributed to one author as their published taxonomy. A preferred digital candidate remains distinct from a physically qualified design.
