# Passive GBJ cooling qualification protocol

This protocol is a proposal for a qualified engineer. It authorizes no mains
operation by itself. It closes the installed-cooling question only when the
exact bridge, sink, fan, duct and board revision are identified in the run
record.

## Apparatus and identity

Record the bridge manufacturer/MPN and lot, board SHA-256, sink and fan MPNs,
interface materials, clamp force or torque, fan supply and tach capture, ambient
temperature, enclosure panels and duct geometry. Calibrate the airflow probe,
thermocouples or RTDs, voltage probes and current probe before the run.

Measure airflow at the fin inlet and outlet with the final grille and enclosure
installed. A free-air fan rating is not an installed-flow result. Capture the
fan pressure or static pressure at the same operating point so the 100 CFM
requirement can be reproduced.

## Electrical and thermal run

1. Inspect for solder voids, lead strain, spreader flatness, isolation and
   independent mechanical support. Do not run if the sink loads the PCB.
2. At ambient 25 °C and 40 °C, run the passive bridge at 25%, 50%, 75% and
   100% of the 15 A RMS design current. Capture bridge terminal voltage and
   current simultaneously over an integer number of line cycles; compute
   bridge real loss from the synchronized waveforms.
3. Hold each point until bridge case, spreader, sink inlet/outlet and the four
   bridge-side board contacts drift by less than 1 °C over 10 minutes. Log fan
   tach and installed flow continuously.
4. Repeat the 100% point with the enclosure at the specified maximum ambient,
   and with the fan at its measured minimum acceptable speed. Do not call this
   a fan-failure test; a separate shutdown response is required.
5. Run an authorized controlled fan-stop or airflow-loss test only with an
   independent power cutoff and a documented maximum energy exposure. Record
   cutoff latency and the peak temperatures; the passive model has no transient
   shutdown proof.

## Acceptance rules

The run is accepted only if all of these hold at the worst measured point:

* bridge real loss is no greater than the 40 W design allowance, or the cooling
  design is re-sized using the measured value;
* installed fin-path flow is at least 100 CFM at the documented pressure point;
* measured forced-flow sink-to-inlet resistance, `(sink temperature - inlet
  air) / total measured heat`, is at most 0.16 K/W for the 60 °C shared-budget
  boundary. The 0.50 K/W catalog value is natural convection and is not an
  alternative acceptance value for this run;
* bridge-side board contacts remain below 110 °C, bridge terminals below 95 °C,
  and the qualified junction estimate remains below 125 °C after applying the
  measured case temperature and the manufacturer's exact thermal datum;
* no temperature, airflow or loss channel is missing, clipped or inferred from
  a free-air rating.

If the loss exceeds 40 W, flow is below 100 CFM, or any temperature limit is
exceeded, the result is **not accepted**. The next action is a cooling redesign
or a loss-reduction decision; it is not permissible to relabel the model as a
worst-case pass. A passing run qualifies only that installed assembly and
identified operating envelope, not every enclosure or lot.

## Evidence package

Retain raw synchronized waveforms, instrument calibration, airflow/pressure
logs, thermal time series, photographs of the mounting and duct, source and
board hashes, and a generated summary. Re-run the existing GBJ numerical replay
against its immutable inputs, then bind the measured loss and thermal boundary
conditions to the run record. Keep hardware qualification separate from the
existing numerical `applicability: indeterminate` result.
