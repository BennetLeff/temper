# Predeclared coupon comparison — no measurements acquired

The outcome is a controlled engineering experiment. Three separately identified configurations are compared: clearance-corrected M222/0.10 mm bond, M222/0.075 mm bond, and complete IST308/0.075 mm experimental assembly. Never swap the element and silently keep the control's bond area, cover mass or lead geometry in the analysis.

## Build and measurement sequence

1. Assign build serial, CAD/BOM hashes, RTD lot, cap stock, bond batch/cure instruction revision and join-process revision. Record substrate/film orientation and installed native lead lengths. Preserve witness sections and mass measurements. Record thickness and void coverage; dispensed volume alone is insufficient.
2. Inspect cap capture, covers, dielectric spacing, joins and harness against exported geometry in unloaded, loaded and extreme travel states. Perform the dry fixture's force/displacement/pressure characterization before thermal fitting. Any sticking or unexplained hysteresis prevents contact-law calibration.
3. Predeclare pan IDs and roles in `campaign.csv`. Keep whole pans assigned to holdout out of fitting and tuning. Suggested preparation minimum: three separately assembled articles per configuration, two fit-family pans and two different holdout pans per article, and three independent placements per pan. These counts are a planning matrix, not a statistical qualification or population guarantee.
4. Acquire initial steady/step points at proposed 50,100,150,200,250°C only within the externally reviewed assembly and fixture limits. Sweep nominal force and the lower/upper verified force envelope; do not assume a spring label establishes actual contact. Measure local pan reference, RTD, cap center/rim where practical, glass, body/anchor, force, displacement and independent contact state on a common clock.
5. Perturb body/anchor temperature while pan temperature is held, then vary applied force with the same pan and bond. These separate experiments help distinguish boundary leakage from contact effects; they still do not uniquely identify every internal network parameter. Record sensor attachment heat shunting.
6. Fit the effective model only on assigned fit runs. Freeze its parameters, input identities and fit script hash. Evaluate the same article on distinct holdout pans, changed ramp rates and repeated placement. A failed holdout stays failed; moving it into training requires a newly declared, untouched holdout set.
7. Report signed steady error with expanded uncertainty, pan-step and own-final t90, finite-ramp error, between-placement/build variation and force/body sensitivity separately. Unknown t90 is not zero. Do not subtract fitted offsets from raw accuracy claims or exclude startup to improve the headline.
8. Retest after approved hot/wet, cleaning, thermal-cycle and reassembly exposures. Record the stress schedule and accepted limits before execution. Induction-on tests use the existing dedicated acquisition package and remain a later physical gate.

## Instrument adequacy before accepting results

The proposed whole-system limits are <2°C and <2 s; the <=1°C thermal-only allocation is a development reserve, not a measured instrument budget. Reference placement, spatial gradients, drift, readout, attachment shunting and synchronization all contribute. Use the inherited uncertainty-budget evaluator with justified correlations. A claimed reference accuracy alone is not the complete error budget.

Reference transition plus bounded lag must be <=0.2 s for the new response screen. Sample interval, multiplex delay and event alignment enter `u_time_s`; the acquisition interval must resolve that uncertainty. Inadequate reference bandwidth makes response INDETERMINATE even if the plotted curve looks fast.

Each article requires its own holdout pair. The current fit CLI intentionally rejects cross-cartridge pairs; aggregate cross-build variation is a separate review. Conductive or insulating debris, warm detach, stuck guides/witnesses and advancing frozen readings are fault experiments, never ordinary calibration rows. Use independent separation ground truth and the fixture protocol. No successful thermal fit closes the contact-inhibit gate.

All proposed acquisition rows remain `NOT_RUN`. Product limits for seal leakage, retention abuse, service life and cleaning media still require definition; no numeric values are fabricated here.
