# Source-topology standby interface

`PFC_STANDBY aux15 permit vsense gnd` reproduces the retained source's two
AO3400A topology:100k/100k inhibit-gate divider,1k permit-gate resistor and
100k pulldown. High permit turns on the lower transistor and releases VSENSE;
low or floating permit lets the upper transistor clamp VSENSE. For the coupled
candidate, the permit input is the local protection `enable_good` node so loss
of health is dominant. Isolated external ARM/PERMIT generation remains a port
contract; this does not implement its isolation barrier.

The nominal MOS VTO1.05V and capacitance anchors are from the
[AOS AO3400A Rev3.1 datasheet](https://www.aosmd.com/res/data_sheets/AO3400A.pdf):
Ciss630pF, Coss75pF, Crss50pF at VDS15V/VGS0V/1MHz. KP20 and RD/RS5mΩ are
explicit authored assumptions, and the constant capacitances are not a fitted
charge model. Published gate absolute rating is ±12V. Neither these typical
anchors nor the doubled-capacitance sensitivity run establish worst-case delay.

The SPICE fixture passes five windows: default standby, release, driven-low
permit, repeated release, and floating-permit recovery. Gate voltages remain
inside ±12V. The same windows pass with capacitances doubled. Removing the
inhibit transistor produces the expected `default standby violated` failure.
This is a source-topology screen, not silicon or arbitrary brownout qualification.
The fast driver inhibit remains an independent path; this slower standby clamp
is not credited with the entire protective current-cessation deadline.

Run ngspice on each .cir, compile checks.rs using rustc, and check each TSV.
The broken fixture must fail for the exact stated reason. Rust validates exact
probe names, finite values, time order/gaps and end time before functional checks.
