* Conditional UCC28180D behavioral model for B1/B2 fixture.
*
* This is not a TI macro-model.  No manufacturer model could be retrieved in
* the bounded three-attempt window (see model-retrieval.log).  The terms below
* are the datasheet functional equations/thresholds only: 5-V VSENSE
* reference, 11.5/9.5-V VCC UVLO, 0.82-V standby/OLP, 5.25/5.35-V OVP_L
* (nominal 105/107% of 5 V), 5.45-V OVP_H (109%), 5.10-V reset (102%),
* -0.285-V SOC, -0.400-V PCL and 300-ns leading-edge PCL blanking.
*
* Pins/nets supplied by the fixture: vcc, vsense, isense, run, gate, vcomp.
* The gate is a sampled oscillator at the FREQ-selected 130 kHz design point;
* duty is a function of VSENSE/VCOMP and the live ISENSE signal, never a fixed
* PWM waveform.  The current/voltage loop transconductance and internal ramp
* are reduced-order approximations.  Results remain conditional for dynamics,
* soft-start timing, line-cycle current shaping, and stability.

.param UCC_VREF=5
.param UCC_VCCON=11.5
.param UCC_VCCOFF=9.5
.param UCC_VSTBY=0.82
.param UCC_VOVP_L=5.35
.param UCC_VOVP_H=5.45
.param UCC_VOVP_RST=5.10
.param UCC_VSOC=-0.285
.param UCC_VPCL=-0.400
.param UCC_TPCL_BLANK=300n
.param UCC_FSW=130k
.param UCC_TSW={1/UCC_FSW}
.param UCC_CVCOMP=4.7u
.param UCC_RVCOMP=4k
.param UCC_DMAX=0.96
.param UCC_VGATE=12

* Datasheet §8.3.13 current-loop gain pieces (M1 and M2, equations 81–88).
* They are exposed as observability nodes and contribute a bounded inner-loop
* correction below; the missing encrypted macro-model still prevents a claim
* of exact internal PWM-ramp dynamics.
Bm1 ucc_m1 0 V={(V(vcomp)<1) ? 0.068 : ((V(vcomp)<2) ? 0.156*V(vcomp)-0.0881 : ((V(vcomp)<4.5) ? 0.313*V(vcomp)-0.4012 : 1.007))}
Bm2 ucc_m2 0 V={(V(vcomp)<0.5) ? 0 : ((V(vcomp)<4.6) ? (UCC_FSW/65k)*0.1223*(V(vcomp)-0.5)^2 : (UCC_FSW/65k)*2.056)}
Rgm1 ucc_m1 0 1meg
Rgm2 ucc_m2 0 1meg

* VCOMP: datasheet's 1.5-V precharge and 40-uA soft-start source while
* VSENSE<4.25 V; 4-kOhm rapid discharge when OVP_L/standby/UVLO is active.
* ngspice current is positive from the named first node to ground, so a
* negative source charges VCOMP and a positive source discharges it.
Cvcomp vcomp 0 {UCC_CVCOMP} IC=0
Rvcomp_bleed vcomp 0 1G
Covp_latch ucc_ovp_latch 0 1u IC=0
Rovp_latch_bleed ucc_ovp_latch 0 1G
Bovp_latch ucc_ovp_latch 0 I={(V(vsense)>UCC_VOVP_H) ? -5m : ((V(vsense)<UCC_VOVP_RST) ? 5m : 0)}
Bvcomp vcomp 0 I={(V(vcc)<UCC_VCCOFF || V(vsense)<UCC_VSTBY || V(vsense)>UCC_VOVP_L || V(run)<0.5) ? max(V(vcomp),0)/UCC_RVCOMP : ((V(vcomp)<1.5) ? -1m : ((V(vsense)<4.25) ? -40u : -40u*(UCC_VREF-V(vsense))/0.75))}

* Gate output: oscillator phase is explicit.  The feedback term is bounded and
* includes a VCOMP-dependent duty command.  PCL is cycle-by-cycle after the
* 300-ns leading-edge blanking interval; OVP_H and UVLO inhibit all pulses.
Bgate gate 0 V={(V(vcc)<UCC_VCCOFF || V(vsense)<UCC_VSTBY || V(vsense)>UCC_VOVP_H || V(ucc_ovp_latch)>2.5 || V(run)<0.5) ? 0 : (((time-UCC_TSW*floor(time/UCC_TSW))<UCC_TSW*limit(0.04+0.32*V(ucc_m1)*V(vcomp)+0.02*V(ucc_m2)*(UCC_VREF-V(vsense)),0,UCC_DMAX) && ((time-UCC_TSW*floor(time/UCC_TSW))<UCC_TPCL_BLANK || V(isense)>UCC_VPCL) && ((time-UCC_TSW*floor(time/UCC_TSW))<UCC_TPCL_BLANK || V(isense)>UCC_VSOC)) ? UCC_VGATE : 0)}

* Observability pins for the Rust verdict parser.
Buvlo ucc_uvlo 0 V={(V(vcc)>UCC_VCCON) ? 5 : 0}
Bstandby ucc_standby 0 V={(V(vsense)<UCC_VSTBY) ? 5 : 0}
Bovp ucc_ovp 0 V={(V(vsense)>UCC_VOVP_H) ? 5 : 0}
Bsoc ucc_soc 0 V={(V(isense)<UCC_VSOC) ? 5 : 0}
Bpcl ucc_pcl 0 V={(V(isense)<UCC_VPCL && (time-UCC_TSW*floor(time/UCC_TSW))>UCC_TPCL_BLANK) ? 5 : 0}

Rgate gate gate_int 10
Cgate gate_int 0 1n
Rgatepd gate_int 0 10k
.save v(vcc) v(vsense) v(isense) v(run) v(gate) v(gate_int) v(vcomp) v(ucc_m1) v(ucc_m2) v(ucc_ovp_latch) v(ucc_uvlo) v(ucc_standby) v(ucc_ovp) v(ucc_soc) v(ucc_pcl)
