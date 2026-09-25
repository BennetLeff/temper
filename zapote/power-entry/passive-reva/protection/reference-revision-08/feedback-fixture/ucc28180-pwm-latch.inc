* Host-authored nominal UCC28180 functional surrogate; NOT TI macro-model.
* TI RevD sections8.3 and eq81..88,100. Full nonlinear silicon dynamics unknown.
* External pins VCC VSENSE ISENSE ICOMP VCOMP GATE GND; RFREQ parameter.
* FSW fitted source calculation16.2k=129107Hz, not oscillator corner bound.
.subckt UCC28180_FN vcc vsense isense icomp vcomp gate gnd params: RFREQ=16.2k PCL_ENABLE=1
.param FSW={2.0915334e9/RFREQ} PERIOD={1/FSW} K1=7 GMI=.95m
.func clip(x,lo,hi) {min(max(x,lo),hi)}
Vfive five gnd 5
* Hysteretic states: UVLO11.5V on/9.5V off; OVP5.45V set/5.10V reset.
Suv five uv vcc gnd UVSW
Ruv uv gnd 1k
.model UVSW SW(Ron=1 Roff=1e12 Vt=10.5 Vh=1)
Sov five ov vsense gnd OVSW
Rov ov gnd 1k
.model OVSW SW(Ron=1 Roff=1e12 Vt=5.275 Vh=.175)
Bfault fault gnd V=(V(uv,gnd)<2.5 || V(vsense,gnd)<.82 || V(isense,gnd)>.085 || V(icomp,gnd)<.2) ? 5 : 0
* ICOMP short below0.2V is a fault and inhibits PWM; its integrator is not
* forcibly reset (the reset causes are declared separately below).
* ICOMP short remains a PWM/VCOMP inhibit, but it is not a reset source for
* the ICOMP integrator.  TI 8.3.17 resets ICOMP only for UVLO/VSENSE/ISENSE
* and OVP conditions; conflating ICOMP<0.2 with reset creates a .2-V chatter.
Bicomp_reset icomp_reset gnd V=(V(vsense,gnd)<.82 || V(isense,gnd)>.085 || V(ov,gnd)>2.5) ? 5 : 0
* Explicit externally compensated voltage amplifier, sourced toward VCOMP.
* 1mA precharge below1.5V;40uA startup below85%; otherwise56uS/EDR280uS.
Bss_done_raw ss_done_raw gnd V=(V(vsense,gnd)>4.9 && V(fault)<2.5) ? 5 : 0
Ass_inputs [five ss_done_raw fault] [ss_data ss_clk ss_reset] UADC
Ass ss_data ss_data ss_clk ss_reset ss_q ss_qn UDFF
Ass_out [ss_q] [ss_done] UDAC
* Powered OLP nominal80ohm from0.04V@0.5mA; bias-absent equivalent5.405k
* from0.37mA@2V. These are condition-specific nominal approximations.
Bvamp gnd vcomp I=(V(fault)>2.5) ? -V(vcomp,gnd)/((V(vcc,gnd)<.1) ? 5405.405 : 80) : ((V(vsense,gnd)>5.35 || V(isense,gnd)<-.285) ? -V(vcomp,gnd)/4k : ((V(ss_done)<2.5 && V(vcomp,gnd)<1.5) ? 1m : ((V(ss_done)<2.5 && V(vsense,gnd)<4.25) ? 40u : ((V(ss_done)>2.5 && (V(vsense,gnd)>5.25 || V(vsense,gnd)<4.75)) ? clip((5-V(vsense,gnd))*280u,-275u,275u) : clip((5-V(vsense,gnd))*56u,-40u,40u)))))
* Nonlinear gain + PWM slope from TI equations81..88.
Bm1 m1 gnd V=(V(vcomp,gnd)<1) ? .068 : ((V(vcomp,gnd)<2) ? .156*V(vcomp,gnd)-.088 : ((V(vcomp,gnd)<4.5) ? .313*V(vcomp,gnd)-.401 : 1.007))
Bm2 m2 gnd V=(V(vcomp,gnd)<.5) ? 0 : ((V(vcomp,gnd)<4.6) ? (FSW/65k)*.1223*(V(vcomp,gnd)-.5)^2 : (FSW/65k)*2.056)
* Current averaging pole GMI*M1/(K1*Cicomp), TIeq100;±50uA nominal linear-range approximation.
* TI 8.3.17 current-loop operating point includes the 0.72-V ICOMP floor:
* ICOMP=.72 + K1*(-2.5*ISENSE)/M1, bounded to the nominal .72..6-V range.
* Keep the ICOMP-short inhibit in Bfault, but do not let it create an
* algebraic .2-V reset chatter.  The .72-V offset is source-derived model
* behavior, not a silicon tolerance claim.
Biamp gnd icomp I=(V(icomp_reset)>2.5) ? (3-V(icomp,gnd))/100 : clip(GMI*V(m1)/K1*(clip(.72+K1*(-2.5*V(isense,gnd))/max(V(m1),.068),.72,6)-V(icomp,gnd)),-50u,50u)
Bphase phase gnd V=time-PERIOD*floor(time/PERIOD)
Vclock cycle_reset gnd PULSE(5 0 20n 1n 1n {PERIOD-22n} {PERIOD})
* Figure-28 inference: the ramp sits at the .72-V baseline during tOFF_MIN,
* then rises with M2.  .72 is E2E/datasheet-min-off evidence, not a silicon
* tolerance claim; the 570-ns timing remains a nominal surrogate parameter.
Braw raw gnd V=(V(phase)>570n && (.72+V(m2)*1e6*(V(phase)-570n))>V(icomp,gnd)) ? 5 : 0
* The TI block diagram places a PWM SR latch between the PWM comparator
* and the gate pre-driver: comparator output drives S, oscillator/min-off
* clock drives R. A direct comparator-to-gate wire chatters when ICOMP
* changes during a cycle and is therefore not a faithful cycle hold.
Apwm_inputs [five raw cycle_reset] [pwm_data pwm_clk pwm_reset] UPWM_ADC
Apwm pwm_data pwm_clk NULL pwm_reset pwm_q pwm_qn UDFF
* Explicit analog bridge for the held PWM state; no implicit digital conversion.
Apwm_out [pwm_q] [pwm_hold] UPWM_DAC
* Blanking measured from the held PWM latch leading edge.
Cblank blank gnd 1p IC=0
Bblank gnd blank I=(V(pwm_hold)>2.5) ? 1u : -V(blank)/1
Bpcl_request pcl_request gnd V=(PCL_ENABLE>.5 && V(pwm_hold)>2.5 && V(blank)>.3 && V(isense,gnd)<-.4) ? 5 : 0
Apcl_inputs [five pcl_request cycle_reset] [pcl_data pcl_clk pcl_reset] UADC
Apcl pcl_data pcl_clk NULL pcl_reset pcl_q pcl_qn UDFF
Apcl_out [pcl_q] [pcl_hold] UDAC
.model UADC adc_bridge(in_low=2.5 in_high=2.5)
.model UPWM_ADC adc_bridge(in_low=2.5 in_high=2.5 rise_delay=1n fall_delay=1n)
.model UDFF d_dff(clk_delay=1n reset_delay=1n set_delay=1n rise_delay=1p fall_delay=1p ic=0)
.model UDAC dac_bridge(out_low=0 out_high=5 out_undef=2.5)
* An unknown digital PWM state must keep the analog output off.
.model UPWM_DAC dac_bridge(out_low=0 out_high=5 out_undef=0 t_rise=1n t_fall=1n)
* Preserve the explicit DAC finite edge; re-thresholding it creates an
* ideal voltage step at a mixed-signal event and can prevent convergence.
Bgate gate gnd V=(V(fault)<2.5 && V(ov)<2.5 && V(pcl_hold)<2.5) ? min(V(vcc,gnd),15.2)*clip(V(pwm_hold)/5,0,1) : 0
.ends UCC28180_FN
