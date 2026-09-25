* Retained source two-AO3400A standby topology; nominal authored MOS model.
* No qualified timing/temperature/back-power claim. gnd may be nonzero.
.subckt PFC_STANDBY aux15 permit vsense gnd params: CAP_SCALE=1
Rup aux15 inhibit_gate 100k
Rdown inhibit_gate gnd 100k
Rpermit permit permit_gate 1k
Rpermitpd permit_gate gnd 100k
Minhibit vsense inhibit_gate gnd gnd AO3400_NOM
Mpermit inhibit_gate permit_gate gnd gnd AO3400_NOM
* AOS Rev3.1 Ciss630p/Coss75p/Crss50p at VDS15,VGS0,1MHz typical.
* Constant capacitances are a sensitivity model, not charge-curve validation.
Cigs inhibit_gate gnd {580p*CAP_SCALE}
Cigd inhibit_gate vsense {50p*CAP_SCALE}
Cids vsense gnd {25p*CAP_SCALE}
Cpgs permit_gate gnd {580p*CAP_SCALE}
Cpgd permit_gate inhibit_gate {50p*CAP_SCALE}
Cpds inhibit_gate gnd {25p*CAP_SCALE}
* VTO1.05 nominal; KP20 and RD/RS5m chosen approximation, not vendor fit.
.model AO3400_NOM NMOS(VTO=1.05 KP=20 RD=5m RS=5m L=1u W=1u)
.ends PFC_STANDBY
