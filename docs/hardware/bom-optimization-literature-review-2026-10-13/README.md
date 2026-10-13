---
title: Literature review for Temper BOM optimization
date: 2026-10-13
type: literature-review
---

# Literature review for Temper BOM optimization

The literature supports analyzing required functions, process costs and component compatibility before deciding whether a cheaper BOM is a better design. It provides conditional models and methods; it does not establish automatic savings from fewer parts, fewer suppliers or more standardization. The main change to our proposal is to treat those counts as explanatory inputs and require a credible cost mechanism for each claimed gain.

This review examines **13 sources**: a textbook preview, two papers with accessible full text, six papers available only as abstracts/summaries, three organizational method pages and one official vendor fee article. Access depth is explicit below. No source was used to claim a validated improvement on Temper.

## Scope and search method

This is a targeted critical narrative review of BOM economics, DFMA, commonality, component qualification, lifecycle and sourcing. Searches used the themes in [sources.json](sources.json), followed references and author/publication links, and favored original papers, publishers, research-group pages and official process documentation. Retrieval occurred on 2026-10-13. Foundational research was retained for its decision models; current vendor documentation was checked separately for changing process rules.

The review is not an exhaustive search or meta-analysis, and it does not establish the latest consensus in every field. Paywalled full papers, inaccessible official documents and unreviewed chapters are recorded as gaps rather than inferred from snippets. Commercial savings percentages and anonymous optimization advice were excluded from the evidence used for expected results.

The earlier [six book rubrics](../pcb-reference-rubrics-2026-10-13/README.md) remain the technical background. Their previous targeted reading was not repeated here. This new review supplies economic and selection-method grounding for the [BOM strategy](../bom-benchmark-optimization-strategy-2026-10-13.md), whose scoring and comparison rules remain our own engineering composition.

## Sources and findings

### L01 FHWA, The Value Engineering Process and Job Plan

**Evidence:** Government method guidance. **Read:** Relevant page text read. **Locator:** Definition and seven job-plan phases.

Function analysis precedes alternatives and their evaluation against life-cycle cost and performance. This supports asking what a block must do before trying cheaper implementations. The method comes from infrastructure practice; adapting it to electronics is an engineering inference. It does not establish Temper acceptance limits or require strict technical improvement alongside every cost saving. [Source](https://www.fhwa.dot.gov/ve/veproc.cfm).

### L02 Boothroyd, Dewhurst and Knight, Product Design for Manufacture and Assembly, 3rd ed.

**Evidence:** Textbook publisher preview. **Read:** 71-page preview; targeted body reading. **Locator:** Printed pp. 1, 8–17, 30–32; PDF pp. 40, 47–56, 69–71; Chapter 6 TOC only.

DFMA combines assembly simplification with process-cost evaluation and can support benchmarking and early estimates. The three theoretical separation criteria concern motion, material/isolation and assembly/disassembly. Practical and economic constraints can still justify a separate part. These are mechanical assembly criteria, not a test for deleting resistors or protection devices. PCB costing Chapter 6 appears in the contents but its body was unavailable in this preview. [Source](https://api.pageplace.de/preview/DT0400.9781420089288_A37928772/preview-9781420089288_A37928772.pdf).

### L03 Ellram, Total cost of ownership: an analysis approach for purchasing

**Evidence:** Peer-reviewed purchasing case-study paper. **Read:** Publisher abstract only. **Locator:** International Journal of Physical Distribution & Logistics Management 25(8), 4–23; abstract.

The abstract describes purchase-related costs beyond acquisition price and a study of 11 firms using TCO. It supports a broader purchasing-cost boundary, while providing no Temper cost coefficients. The full cases and model examples were not accessed; detailed claims about their implementation or effectiveness would exceed this reading. [Source](https://doi.org/10.1108/09600039510099928).

### L04 Ferrin and Plank, Total Cost of Ownership Models: An Exploratory Study

**Evidence:** Peer-reviewed exploratory purchasing study. **Read:** Publisher summary only. **Locator:** Journal of Supply Chain Management 38(2), 18–29; SUMMARY; issue year 2002, publisher online posting displays 2006.

The summary favors a common core of cost drivers supplemented by purchase-specific drivers, rather than one generic TCO model. Temper should therefore justify each costing term instead of importing an exhaustive checklist or unsupported overhead factors. The complete dataset, sampling limitations and driver tables were not available. [Source](https://doi.org/10.1111/j.1745-493X.2002.tb00132.x).

### L05 Labro, The Cost Effects of Component Commonality: A Literature Review Through a Management-Accounting Lens

**Evidence:** Peer-reviewed literature review. **Read:** Publisher abstract only. **Locator:** Manufacturing & Service Operations Management 6(4), 358–367; abstract.

The author distinguishes cost-driver and cost-rate effects and rejects an unconditional claim that more commonality lowers total cost. She describes much of the literature as theoretical and empirical evidence as limited. This supports treating fewer unique MPNs as a hypothesis, not an economic verdict. The full reviewed-paper set was not examined, so this is her reported conclusion rather than a new systematic replication. [Source](https://doi.org/10.1287/msom.1040.0047).

### L06 Thonemann and Brandeau, Optimal Commonality in Component Design

**Evidence:** Peer-reviewed analytical model with automotive application. **Read:** Full text accessible through web; targeted sections read. **Locator:** Operations Research 48(1), 1–19; §§2–3, §5 cost estimation, §6 Tables 2–3, §8 discussion.

The model balances production, inventory, setup and complexity costs. Its wire-harness application favors partial sharing over both extreme designs; results change with demand and complexity assumptions. The modeled features must satisfy each assigned requirement. This supports a compatibility-constrained search with sensitivity analysis. Its additive features, replenishment policy and demand assumptions do not automatically model PCB parts, qualification expense or startup overhead. [Source](https://pubsonline.informs.org/doi/pdf/10.1287/opre.48.1.1.12445).

### L07 Lyly-Yrjänäinen, Lahikainen and Paranko, Cost effect of component commonality: manufacturing cost perspective

**Evidence:** Conference action-research case study. **Read:** 10-page full text; OCR and targeted image verification. **Locator:** NordDesign 2004, pp. 371–380; §§2–5, especially Table 3 on printed p. 378 / PDF p. 8.

A conveyor motor-support case shows why the measurement level matters. Version 3 has 18 parts and 8 component types, versus 12 and 6 for Version 2, but reduces stocked subassembly IDs from 8 to 4. Manufacturing cost rises from €91 to €97; the paper leaves wider overhead benefits unresolved. This is a counterexample to using one count as the winner. The figures are historical case data, not Temper savings estimates. [Source](https://www.designsociety.org/download-publication/29213/cost_effect_of_component_commonallty_manufacturing_cost_perspective).

### L08 Jackson, Sandborn, Pecht, Hemens-Davis and Audette, A risk-informed methodology for parts selection and management

**Evidence:** Peer-reviewed electronics selection methodology. **Read:** Author-hosted abstract and publisher metadata. **Locator:** Quality and Reliability Engineering International 15(4), 261–271; abstract.

Selection separates availability, cost and manufacturer/distributor integrity from application-specific environment, performance, reliability, assembly and obsolescence. This supports distinguishing purchasing identity from in-circuit qualification. The complete procedure was unavailable, so it cannot supply an adopted qualification checklist or numerical risk weights. [Source](https://web.calce.umd.edu/articles/abstracts/1999/Risk_inf.htm).

### L09 CALCE, Part Selection and Management Benchmarking Services

**Evidence:** Research-group process description. **Read:** Relevant page text read. **Locator:** Risk-informed methodology bullets and benchmarking description.

CALCE describes requirements, manufacturing/handling constraints, local environments and supportability as parts-selection inputs, and uses fact finding to assess organizational practice. This is useful electronics-specific process guidance, but it is a services description from the same research group as L08, not independent validation of Temper or our scoring system. [Source](https://calce.umd.edu/part-selection-and-management-benchmarking-services).

### L10 CALCE, Mitigation of Obsolescence Cost Analysis

**Evidence:** Research-group model description. **Read:** Relevant page text and bibliography read. **Locator:** Lifecycle mismatch, mitigation alternatives and MOCA analysis sections.

Obsolescence decisions include substitution, lifetime buys and redesign, with engineering and requalification costs. MOCA compares refresh timing/content using production, maintenance and forecast inputs. This supports recording future change burden and support horizon. Its long-life avionics/military context may overweight sustainment for Temper; linked full papers were inaccessible and no model was reproduced. [Source](https://calce.umd.edu/mitigation-obsolescence-cost-analysis-moca).

### L11 Tomlin, On the Value of Mitigation and Contingency Strategies for Managing Supply Chain Disruption Risks

**Evidence:** Peer-reviewed analytical sourcing model. **Read:** Publisher abstract only. **Locator:** Management Science 52(5), 639–657; abstract.

The model compares inventory, reliable sourcing and contingency strategies under supplier capacity, disruption patterns and risk preferences. Its reported results support evaluating actual recovery capability and disruption duration, rather than treating source count as resilience. The full proofs and model were not read. Applying this to upstream manufacturer dependence is our inference, not a result established by the accessible abstract. [Source](https://doi.org/10.1287/mnsc.1060.0515).

### L12 JLCPCB, PCB Assembly Cost: What Does the Price Include?

**Evidence:** Official vendor fee documentation. **Read:** Fee table and explanations read. **Locator:** Page updated 2026-09-09; setup, SMT/manual assembly, feeder loading and inspection sections.

The current fee structure distinguishes per-order, per-side, per-joint, loading and inspection charges. Economic PCBA charges loading for extended parts; Standard PCBA charges loading for basic and extended parts. Thus catalogue category savings depend on assembly route and quantity. This is dated vendor policy, not independent research or a quote for this board. No tariff numbers are adopted as permanent costing constants. [Source](https://jlcpcb.com/help/article/pcb-assembly-price).

### L13 Syrus, Pecht and Humphrey, Part Assessment Guidelines and Criteria for Parts Selection and Management

**Evidence:** Peer-reviewed electronics assessment methodology. **Read:** Author-hosted abstract only. **Locator:** IEEE Transactions on Electronics Packaging Manufacturing 24(4), 339–350; abstract.

The authors describe assessing acquired part data against predetermined criteria and report a 113-part case study. This supports making acceptance criteria explicit before evaluating a part. The actual criteria and results were not accessible; it provides no validation of our 20 criteria and no basis for claiming their thresholds or predictive accuracy. [Source](https://web.calce.umd.edu/articles/abstracts/2001/part.htm).

## What this changes in the proposal

| Interpretation to assess | Literature disposition | Implication for Temper |
|---|---|---|
| Optimize required function and installed cost | Supported as a method by L01, L03 and L04 | Record functions and purchase-specific drivers before searching substitutes |
| Use part-count reduction as a shortcut to savings | Not supported as a universal result; L05–L07 | Compare placements, unique MPNs and stocked assemblies separately |
| Apply minimum-part criteria to every circuit part | Mechanical scope in L02 | Use electrical function/stress evidence for circuitry; use DFA on attachment and assembly structure |
| Share one component across many roles | Conditional trade-off in L06 | Validate compatibility and the cost of unnecessary capability; test cost assumptions |
| Tailor a costing model to Temper | Supported by L04; process specificity in L12 | Distinguish avoidable cost, allocated overhead, capacity/time benefits and one-time work |
| Count suppliers as resilience | Insufficient; L11 is a capacity/disruption model | Identify manufacturer dependence, approved substitutions and recovery capacity |
| Track qualification and future redesign burden | Method support in L08–L10/L13 | Preserve unanswered requirements and future change costs instead of assuming interchangeability |
| Freeze our own corrected benchmark | Our experimental-control choice | Preserve matched assumptions and source identities; the reviewed sources do not prescribe our file protocol |
| Require cheaper/simpler AND technically better | User's chosen objective | Equivalent required function at lower cost can be a valid literature outcome, but may not satisfy this stronger project goal |
| Delay broad supplier outreach until a shortlist | Project scheduling choice | Collect decisive feasibility/process facts earlier when needed; no reviewed source guarantees they can all wait |

## Proposed application to Temper

The following is our synthesis, not a published optimization algorithm. Preserve the intended benchmark workflow, then test separate hypotheses for purchasing, compatible substitution, assembly simplification and functional redesign. Use the [claim and rubric map](claim-evidence-map.md) to keep source-backed principles distinct from project decisions.

Compare economics across at least the agreed prototype and intended production scenarios. Keep one-time changes, recurring avoidable costs, inventory exposure and capacity benefits visible. A simple break-even calculation may help when costs are approximately fixed or linear; discounts, setup changes, yield and service assumptions require scenario calculations instead. These calculations still need Temper data.

Commonality models need the correct demand structure. **Our inference from L06:** when several parts are consumed together by the same board, their demand co-moves; crediting independent-demand inventory pooling merely because their MPNs merge would be unjustified. Across variants or products, use the actual consumption relationships and uncertainty. Also avoid importing a large manufacturer's overhead cost per variant into a small project.

Prioritize hypotheses that might improve both cost and behavior, while retaining equivalent-performance cost savings as useful contributors. Evaluate interacting changes together before choosing a board candidate. No literature result gives permission to weaken a critical requirement or to replace component characterization with a procurement label.

## Reading limitations and remaining evidence

L03, L04, L05, L08, L11 and L13 support only the accessible abstract/summary statements. Their full empirical methods, coefficients, proofs and detailed selection criteria were not read. L06's model was examined, not reproduced or calibrated to Temper. L07 is one mechanical action-research case; its OCR was checked against the key scanned table. L02 is a 71-page publisher preview, not a reading of the full textbook or its PCB Chapter 6. CALCE method pages are related sources, not multiple independent validations. Vendor documentation describes one route at one date.

The corpus provides methods and counterexamples, not an empirical forecast for a hot induction power board. To make a decision, we still need the intended quantities, accepted-unit cost boundary, exact approved parts, process constraints, comparable quotes, credible assembly/yield data and the technical validation appropriate to each change. Current distributor stock, component prices and actual alternatives were not surveyed here.

The highest-value further reading would be the full TCO/commonality/parts-assessment papers and the textbook's PCB costing chapter. Specific market/product qualification requirements and actual component manufacturer data belong to the later candidate assessment; organizational guidance does not set those limits.

## Evidence retention

[sources.json](sources.json) records bibliography, access depth, locators, retrieval date and the hashes of the two locally downloaded source PDFs. Original reading copies, extraction and OCR are retained under `/private/tmp/temper-bom-literature-2026-10-13/`; copyrighted source PDFs are not republished in this repository. Publication year comes from the source/issue rather than search-engine crawl dates. [The claim map](claim-evidence-map.md) records how this review changes the proposal without grading or altering the BOM.
