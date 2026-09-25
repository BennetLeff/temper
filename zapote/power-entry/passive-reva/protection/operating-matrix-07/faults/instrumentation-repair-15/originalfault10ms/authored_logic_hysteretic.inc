* Authored bounded interface with one collapsed output node.
* Pins: INM (active-high disable), INP (PWM), VDD (auxiliary supply), GND,
* OUT (collapsed source/sink output). It intentionally does not pretend to
* reproduce the TI model's separate OUTH/OUTL current paths.
.subckt AUTH_UCC27511A_H INM INP VDD GND OUT
* Fixed 1 V logic reference makes each native SW state a 0/1 state. The
* states are authoritative hysteresis elements; Bdriver_req only combines
* their qualified values and scales by VDD.
Vlogic logic_ref GND 1
.model SW_PWM_H SW(Ron=1 Roff=1e9 Vt=1.7 Vh=.5)
.model SW_INM_H SW(Ron=1 Roff=1e9 Vt=1.7 Vh=.5)
.model SW_AUX_H SW(Ron=1 Roff=1e9 Vt=4.05 Vh=.15)
* Retain the nominal input loading represented by the vendor macro model.
Rinm_pull INM VDD 200k
Rinp_pull INP GND 230k
Spwm_state logic_ref pwm_state INP GND SW_PWM_H
Rpwm_state pwm_state GND 100k
Sinm_state logic_ref inm_state INM GND SW_INM_H
Rinm_state inm_state GND 100k
Saux_state logic_ref aux_state VDD GND SW_AUX_H
Raux_state aux_state GND 100k

* Normalize the known switch levels continuously; hysteresis lives only in
* the native SW elements above.  lo/hi are the measured 100 k/1 G and
* 100 k/1 ohm endpoints, so this removes Roff leakage without adding a
* second hard comparator after the authoritative switch state.
.param STATE_LO=9.99900009999e-5 STATE_HI=0.9999900001
Bpwm_logic pwm_logic GND V=min(max((V(pwm_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
Binm_logic inm_logic GND V=min(max((V(inm_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
Baux_logic aux_logic GND V=min(max((V(aux_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)

* PWM high + disable low + AUX valid is the only source request. The output
* pole is retained from the previous finite surrogate as a starting point,
* then one 1 ohm output resistance feeds OUT. This is a finite voltage-source
* approximation, not a claim about UCC27511A source/sink symmetry.
Bdriver_req driver_req GND V=V(VDD,GND)*V(pwm_logic,GND)*(1-V(inm_logic,GND))*V(aux_logic,GND)
Rdriver_delay driver_req drv_delay 1
Cdriver_delay drv_delay GND 18.75n
Routput drv_delay OUT 1
.ends AUTH_UCC27511A_H
