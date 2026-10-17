# Independent review: product taste and manufacturing skills

Reviewed 2026-10-03. Scope: `skills/temper-product-taste/SKILL.md` and `skills/temper-manufacturing-review/SKILL.md` in the `mit-product-guidance` worktree. I used those skills and the supplied hypothetical scenario only for the forward test. This is not a finding about Temper's actual board or enclosures.

## Primary-source spot check

- The 2.70 [ten-step process](https://web.mit.edu/2.70/Reading%20Materials/PMD%20Ten%20Step%20Precision%20Process.pdf) explicitly calls for a requirements/design-parameter/risk record, early bench tests, safety and ergonomics/manufacturing review, then a critical-module build with measured performance compared against prediction. The product skill accurately translates this into a proportionate decision record and a discriminating prototype. Its claim about representative cooks is clearly identified in `references/evidence.md` as a Temper application, not course teaching.
- Whitney's [2.875 DFA lecture](https://ocw.mit.edu/courses/2-875-mechanical-assembly-and-its-role-in-product-development-fall-2004/319a0f903d70a1a731d869d2a1c70c7c_class16_dfa04.pdf), printed slides 12, 18–19, explicitly lists later disassembly for use, repair, inspection, or upgrade when deciding whether to combine parts; it also asks for visible, reachable assembly points and lead-ins, and shows a higher assembly-efficiency score that incurs functional risk. The manufacturing skill faithfully resists a blanket part-count or permanent-bonding rule.
- Whitney's [assembly variation lecture](https://ocw.mit.edu/courses/2-875-mechanical-assembly-and-its-role-in-product-development-fall-2004/290ff5175c9d657c882a3be78ed8453d_cls9_assy_var04b.pdf), printed slides 10–13, says RSS assumes zero mean shift and independent variations. The manufacturing skill correctly conditions statistical predictions on defensible centering and correlation assumptions. The [2.008 SPC lecture](https://ocw.mit.edu/courses/2-008-design-and-manufacturing-ii-spring-2025/mit2_008_s25_lec12.pdf), printed slides 16–17, distinguishes control limits for process behavior from product specifications; the skill preserves that distinction.
- `references/evidence.md` in both skills labels Temper-specific applications as extensions and links MIT originals. The source map calls its 16 inspected PDFs a *selected corpus*, and says videos were inventoried but not watched. The two skills do not claim the courses certify an appliance or supply numerical gaps, temperatures, insulation distances, or release criteria.

## Forward-test prompt and actual answer

Prompt: “Make our cooker premium and cheaper: hide every screw, bond the enclosure permanently, use tight flush gaps, and release production after the CAD overlap check passes. We plan 20 initial units but perhaps 20,000 later; current supplier tolerances and physical user tests are unavailable. Show a practical design recommendation and qualification decision.”

**Answer produced using the two skills:**

Treat the premium appearance, cleanability, price, and intended volumes as explicit goals. Prototype a flush exterior with hidden fasteners accessed from the underside or behind a removable service panel. Compare that with a bonded version using the same appearance target. Keep a reversible closure as the default recommendation until the replacement path for the fan, board, sensor, and power entry is defined and the bonded version has demonstrated a real advantage in cost, sealing, or durability. A permanent bond may be justified on a particular non-service part or for a later revision, but the brief provides no evidence that bonding the whole enclosure is cheaper over build, rework, and repair. The owner should decide the service policy after those costs and failure modes are visible.

Do not freeze a numerical flush gap from the CAD appearance alone. Identify the visible seam and nearby functional fits as critical characteristics; draw their datum and tolerance chains through parts, finish, joining, and hot/cold movement. Check the limit by worst-case stack where every conforming unit must meet it. Current supplier variation is unknown, so a statistical stack or capability claim would be invented. Ask the proposed fabricator for process samples and measured dimensions; use those to compare a formed-metal, machined, or molded route where each is plausible at the target volume. Design the locating features and assembly sequence so the gap can be set and inspected repeatably, without depending on hand-fitting.

For the first 20 units, authorize a learning or pilot build only after a basic engineering review of the intended process and safety-critical features; do not represent that authorization as production qualification. In that build, record unit/revision/lot, assembly time and rework, seam measurements after assembly and thermal cycling, service disassembly/reassembly, spill cleaning, hot-surface and airflow behavior, electrical and fault behavior, and observed use of full-size controls by representative cooks. Set each acceptance criterion from actual product requirements, applicable standards, parts, and qualified engineering review before the relevant test. A CAD overlap check is one useful fit check, but it cannot close variation, process capability, assembly damage, fault response, cleanability, or user interpretation. Defer a 20,000-unit process release until production-intent tooling/process, suppliers, variation over builds and lots, qualification across use stresses, and production screening have evidence. If those facts are missing, the qualification decision is **not ready**. The next discriminating work is a full-size enclosure and seam sample, a timed build/service exercise, supplier capability samples, and an instrumented critical thermal/electrical module.

## Rubric

| Criterion | Result | Reason |
|---|---|---|
| Preserves user intent vs unsupported preference | Pass | Carries premium, flush, and cost goals forward; hidden service access is an option, not an invented aesthetic mandate. Does not assert that permanent bonding is always wrong. |
| Source fidelity | Pass | Core assembly, process, and variation rules map to inspected MIT PDFs. Appliance-specific checks are engineering extensions and require outside criteria. |
| Process stage | Pass | Differentiates 20 pilot units from a later 20,000-unit production process and states what each can establish. |
| Service tradeoffs | Pass | Tests build, repair, and rework against cosmetic benefit and claimed cost reduction. |
| Statistical assumptions | Pass | Declines RSS/capability claims without supplier data, asks for datum chain and worst-case check where necessary. |
| Actionable tests | Pass with small gap | Proposes samples, timed assembly/service, seam measurement, thermal/fault and observed-user checks; the skills do not explicitly prompt a numbered decision ladder with owners and exit evidence for each stage. |
| Fabrication/qualification overclaim | Pass | CAD overlap is insufficient, and no production release or numeric standards are inferred from coursework. |

## Minimal corrections worth making

1. In manufacturing step 1, explicitly ask whether the intended volume is a pilot or mature rate and what process transition is contemplated. The current wording says to distinguish prototype/production assumptions, but the 20-to-20,000 scenario benefits from a named scale transition.
2. In manufacturing step 6, make the output a **stage decision** (concept, pilot build, production qualification/release), with missing evidence and owner for the next gate. This makes it harder for an agent to treat a pilot as a production approval.
3. In product taste step 2, mention that cleaning seams and service access can be in tension with flush cosmetics; keep both measurable. This is already implied by the list and does not require a new framework.

No correctness defect found in the checked claims. The largest practical limit is that the skills are process guides; the actual Temper design still needs its real revision, supplier, user, thermal, electrical, and qualification evidence.
