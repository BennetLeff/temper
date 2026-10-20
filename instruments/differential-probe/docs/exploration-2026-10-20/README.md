# Differential probe improvement studies

**Build decision supersedes the proposed experiment sequence below:** [Rev B build decision](../revb-build-decision.md). Retain the existing 0.1% resistor BOM; cancel the dedicated resistor-comparison experiment. Batteries remain, and pods/lumped dividers stay Rev C candidates pending normal Rev B bench data. The original studies remain research history.

Thirteen GPT-6.1 Sol studies investigated the proposed improvements against Rev B. The strongest cost candidate is the 1% resistor string with a corrected trim network. The largest architectural size opportunities are a lumped divider and separate tip pods. Neither is a drop-in replacement, and their gains should not be added together without designing the combined assembly.

This folder records research, calculations and isolated geometry checks. It does not change the Rev B schematic, BOM or PCB, and no bench qualification was performed. Candidate part numbers are investigation targets, not approved substitutions or live procurement quotes.

## Baseline identity

- Rev B commit: `2f090b305` on `codex/differential-probe-revb`.
- Probe PCB SHA-256: `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`.
- Selected DUT: stage 53, `worktrees/runs-native21/s53/c53int/section.kicad_pcb`.
- Stage-53 PCB SHA-256: `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27`.

The repository's general hardware baseline check concerns a separate candidate; it does not substitute for stage-53 identity or establish probe insulation ratings.

## Comparison

| Proposal | Assessment | Main consequence or next evidence |
|---|---|---|
| [Passive tip pods](01-tip-pods.md) | Promising architectural experiment | Compare captive 0.3 m cable coupons with the bottom network in the pod versus the box. At 5 MHz, coax requires a transmission-line model. Disconnect and shield faults determine the safe architecture. |
| [One HV resistor and lumped top capacitance](02-lumped-divider.md) | Promising size experiment | Suitable bodies can shorten the divider, but 3 kV DC dissipates about 0.9 W. Resistor self-capacitance, voltage coefficient, lead spacing and capacitor AC ratings constrain the choice. |
| [Coating or potting](03-coating-potting.md) | Defer until the assembly is characterized | Potting an unchanged board saves no area. Reduced spacing requires a qualified material/process/assembly; dielectric-strength numbers do not establish working insulation. Final compensation must be measured after cure. |
| [Slot between legs](04-interleg-slot.md) | Moderate gain after component relocation | HV copper geometry sets a 21.375 mm pitch floor before tolerances; existing low-leg parts impose about 31.87 mm. A 22–24 mm target needs those parts moved and the LV section rearranged. |
| [USB power](05a-usb-power.md) | Optional packaging experiment | Removes battery volume, but needs a suitable current source and regulated bipolar conversion. A boost/inverter with retained LDOs is more credible than a simple charge pump; USB adds a parallel ground return. |
| [Single 1000:1 range](05b-single-range.md) | Decide using the actual scope | Removes 13 BOM components and some current. The fine range can still improve scope-limited measurements; upstream probe noise and CMRR do not improve with gain. |
| [Dual amplifiers](05c-dual-amplifiers.md) | Small local optimization | OPA2810 for adjacent U3/U4 is worth evaluating. Combining the widely separated input buffers can worsen sensitive routing. Estimated package courtyard savings are under 0.3% of board area. |
| [AD8130 receiver](05d-differential-receiver.md) | Conditional alternative topology | Replaces several stages, but bias current, finite input resistance and protection alter calibration and per-tip overload sensing. Internal CMRR cannot cancel unequal divider or input parasitics. |
| [1% HV resistors](06-resistor-tolerance.md) | Highest-priority cost experiment | Ideal DC trimming cancels uniform resistance error across frequency. The proposed 4.87 kΩ + 200 Ω network misses corners when pot tolerance is included; adding a suitable fixed resistance restores coverage. Verify voltage coefficient and thermal tracking. |
| [Built-in calibration output](07-calibration-output.md) | Start with an external fixture | A 20 Vpp source needs another supply and careful isolation from measurement pickup. A 60 dB residual is only 20 µVpp at the wide-range output for a 20 Vpp common-mode test. Prefer an externally verified source and a detachable session-check fixture first. |
| [Analog zero](08-analog-zero.md) | Useful, with narrower claims | A quiet buffered adjustment before range selection can correct upstream differential offset in both ranges. One output adjustment cannot correct the individual buffer offsets seen by the per-tip warning comparators. |
| [Delay characterization](09-delay-characterization.md) | Required measurement work | Publish complex gain versus frequency for both ranges and the actual CT path. Stage 53's 3 Ω burden has 100 nF across it: the ideal burden RC alone contributes about 6.45° at 60 kHz. |
| [Single-fault behavior](10-single-fault.md) | Resolve before selecting the next architecture | Existing clamps and LEDs do not establish a safe BNC under a whole-divider bypass. Define available source energy, fault paths and accessible-output criteria, then design and test the protection against them. |

## Corrections that affect the next design

**Area:** Rev B's rectangular HV/LV allocation is approximately 53%/47%, rather than almost entirely HV. The divider determines important dimensions, but shrinking it alone does not shrink the existing LV outline. Battery removal can reduce enclosure volume independently of PCB area.

**Cable compensation:** adding cable capacitance to the bottom capacitor is a low-frequency approximation. The passive, highly mismatched cable network also should not be assigned a simple matched-line flight delay. The pod study uses a transmission-line model and identifies the assumptions that need measurement.

**DC trimming:** 1% upper resistors do not automatically spoil the 35–60 kHz ratio after calibration. The ideal model supports trying them. Their temperature and voltage dependence, and the trimmer's own tolerance and stability, remain material. The approximate cost saving is large, but the report's indexed distributor prices are not current quotes.

**Zero and warning thresholds:** moving the displayed trace to zero does not establish that either input buffer is centered or that the per-tip warning thresholds are correct. Keep individual buffer-offset acceptance checks even if a differential zero control is added.

**Phase:** the calculated 6.45° is the burden RC contribution, not a measured complete CT response. Likewise, the probe report's modeled delays exclude parts of the actual assembly. A single deskew number cannot replace characterization of both complete transfer functions.

**Faults:** a steady-state calculation showing that four surviving sections each see about 750 V does not establish flashover recovery, AC voltage capability or whole-string failure protection. A common-cause surface arc can bypass more than one nominal section.

## Recommended sequence

1. Define the fault-source envelope and accessible-output requirements, and prepare the complete probe/CT gain-and-phase measurement method. These constrain both the centralized and pod architectures.
2. Build low-voltage divider coupons to compare the present string, a 1% string with corrected trim coverage, and a lumped divider. Include voltage-coefficient and temperature tests before accepting the cheaper resistor substitution at high voltage.
3. Compare short captive-cable pod arrangements against the centralized divider. Measure both legs, differential response and common-mode rejection before choosing a package. Pot only sacrificial samples initially; measure again after cure.
4. Evaluate a zero adjustment, actual-scope benefit of the fine range, USB supply noise and the receiver alternatives against that selected architecture. Preserve separate evidence for each change so calibration does not conceal a regression.
5. Only then produce a new integrated schematic/layout and qualify its enclosure, overload recovery, insulation and single-fault behavior.

The individual notes contain manufacturer references, equations, candidate parts and proposed tests. The [slot fixtures](interleg-slot-fixtures/) retain native KiCad boards, rules, projects, JSON reports and command logs for one passing isolated geometry and three deliberately failing controls. They demonstrate the selected geometry constraints; they are not a DRC result for a compacted full PCB or an insulation certification.

## Preservation check

Before saving this research, 97 of the 98 existing tracked probe files matched the Rev B worktree byte for byte, including the schematic, PCB and BOM. The remaining local project file had only a `schematic.top_level_sheets` metadata entry added. That local metadata was preserved and excluded from the research commit. The stage-53 PCB hash matched the identity above; all local report links resolved, and the four archived DRC JSON reports contained the expected passing/negative-control results.
