# Recommendation and handoff

Recommend advancing the **shared 392-120AB concept** as the next modeling
candidate, while retaining the **395-1AB baseline** as the comparison control.
This is a model candidate, not a selected assembly: under the provisional
105 W shared-load screen it reaches 118.64 °C at the bridge junction after
inlet heating, only 6.36 K below the 125 °C ceiling and short of the 15 K
ranking objective.  A bridge-zone resistance at or below about 0.078 °C/W,
or a proven split of the other loads away from the bridge sink path, is needed
to meet that objective.  Do not select the low-profile 396-1AB at the present
40 W allowance: its published 1.07 °C/W forced-convection value produces a
142.8 °C junction screen at 40 °C inlet.

The shared concept is not accepted yet.  Its 0.16 °C/W value is a manufacturer
typical point at 100 CFM for a distributed heat load.  A system model must
prove the bridge-zone resistance with the bridge, PFC switch, diode, inductor
and shunt dissipating together.  It must include inlet heating, duct pressure,
recirculation, mounting orientation and the actual fan curve.  The current
provisional 105 W shared load is a bound to investigate, not a reason to lower
the retained 40 W bridge allowance.

Before a maintained-candidate promotion, owners need:

* exact Yangjie PDF bytes or an explicit source waiver; waveform-bound
  `GBU2510A` loss and temperature dependence;
* bridge lead/solder/barrel geometry and heat partition;
* a dimensioned spreader, clamp, insulation and chassis support drawing;
* a measured or CFD-derived fan/system operating point and flow distribution;
* enclosure collision and service-clearance data (currently **INDETERMINATE**);
* thermal transient/sensor-error evidence establishing a nonempty trip window;
* rerun of the 20-case FEM profile for the frozen connection candidate; and
* physical temperature, airflow and fault qualification, which remains
  **NOT RUN**.

The four `DRC.PFC.BRANCH_COPPER` findings remain open.  Cooling evidence cannot
waive them or establish an IPC current rating.
