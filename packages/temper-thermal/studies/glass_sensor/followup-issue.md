The in-glass PT100 study is now reproducible in `packages/temper-thermal/studies/glass_sensor` on `codex/glass-sensor-simulation`. This issue tracks the physical evidence and contact-validity contract that simulation cannot close. No component or assembly has been qualified.

Simulation evidence:

- 97,200 mechanical combinations, 2,916 thermal cases, 432 candidate corners, 1,152 coupled cases, and 60 radial / 60 controller-module cases.
- CAD-sized geometry under middle assumptions: t90 6.59 s; under-reading 3.19°C at a100°C local pan boundary and5.64°C at200°C with the specified cooler surroundings.
- A favorable thinner-cap candidate reaches1.57 s, but coupled force/recess/partial-contact cases reach4.9 s. Contact conductance is not measured.
- A hot disconnected probe can remain indistinguishable in temperature from a contacting probe. Existing electrical RTD fault checks and liquid-probe detection do not establish in-glass cap contact.
- Module-level PID contact-loss simulations request more heat; the full appliance state machine and hardware protections were deliberately excluded, so this is not a full-system runaway verdict.

Next discriminating work:

- [ ] Mechanical owner: select the exact spring, seal, cap, guide, plunger and wiring; measure complete hot/cold tip-force hysteresis, rest height, return and stroke. Establish smallest supported pan mass, COM offset and local bottom recess. Verify no rocking and no stuck-down state after cleaning/soil exposure.
- [ ] Thermal/materials owner: choose a real RTD and electrically insulating bond with suitable continuous-use and cleaning/aging evidence. The example M222 is0.9 mm nominal thickness versus the CAD0.4 mm envelope. Run the field-free instrumented coupon protocol; fit contact/leakage parameters on one set and validate on separate pans/runs. Apply proposed±2°C /±5°C and t90≤3 s screens including measurement uncertainty.
- [ ] Controls owner: define and prototype an independent contact-valid indication that addresses stuck/debris faults. Demonstrate no temperature-mode heat command without valid contact and inhibit within1 s of confirmed loss while induction pan presence remains true. Integrate with real state-machine and hardware-fault behavior; retune only after identifying the real plant.
- [ ] Integration owner: compare coil-on/off sensor behavior, parasitic cap heating, EMI, local center versus pan-hotspot temperature and glass/aperture/seal temperatures using the actual coil and supported cookware. Repeat force/thermal tests after the proposed1000-cycle screening exposure; do not call it lifetime qualification.

Study artifacts include equations, all assumptions, input/source hashes, raw CSVs, charts, numerical tests and a replay script. The design is suitable for a controlled engineering prototype; production release remains blocked on the evidence above.
