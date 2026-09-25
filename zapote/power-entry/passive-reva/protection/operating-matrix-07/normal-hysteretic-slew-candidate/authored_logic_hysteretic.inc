* Diagnostic-only finite-slew variant of AUTH_UCC27511A_H.
* Native input hysteresis and thresholds are unchanged: PWM/INM 2.2/1.2 V,
* AUX 4.2/3.9 V.  This adds the vendor COMPHYS_BASIC_GEN output pole
* (R=1 ohm, C=5 nF) to each normalized state before Bdriver_req.
* It is a model approximation/sensitivity candidate, not a TI equivalence.
.subckt AUTH_UCC27511A_H INM INP VDD GND OUT
Vlogic logic_ref GND 1
.model SW_PWM_HS SW(Ron=1 Roff=1e9 Vt=1.7 Vh=.5)
.model SW_INM_HS SW(Ron=1 Roff=1e9 Vt=1.7 Vh=.5)
.model SW_AUX_HS SW(Ron=1 Roff=1e9 Vt=4.05 Vh=.15)
Rinm_pull INM VDD 200k
Rinp_pull INP GND 230k
Spwm_state logic_ref pwm_state INP GND SW_PWM_HS
Rpwm_state pwm_state GND 100k
Sinm_state logic_ref inm_state INM GND SW_INM_HS
Rinm_state inm_state GND 100k
Saux_state logic_ref aux_state VDD GND SW_AUX_HS
Raux_state aux_state GND 100k
.param STATE_LO=9.99900009999e-5 STATE_HI=0.9999900001
Bpwm_raw pwm_logic_raw GND V=min(max((V(pwm_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
Binm_raw inm_logic_raw GND V=min(max((V(inm_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
Baux_raw aux_logic_raw GND V=min(max((V(aux_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
* COMPHYS_BASIC_GEN-inspired finite state-output poles; 1 ohm/5 nF => 5 ns.
Rpwmlogic pwm_logic_raw pwm_logic 1
Cpwmlogic pwm_logic GND 5n
Rinmlogic inm_logic_raw inm_logic 1
Cinmlogic inm_logic GND 5n
Rauxlogic aux_logic_raw aux_logic 1
Cauxlogic aux_logic GND 5n
Bdriver_req driver_req GND V=V(VDD,GND)*V(pwm_logic,GND)*(1-V(inm_logic,GND))*V(aux_logic,GND)
Rdriver_delay driver_req drv_delay 1
Cdriver_delay drv_delay GND 18.75n
Routput drv_delay OUT 1
.ends AUTH_UCC27511A_H
