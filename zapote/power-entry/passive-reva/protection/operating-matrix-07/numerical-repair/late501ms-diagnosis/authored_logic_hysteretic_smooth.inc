* Diagnostic-only variant: retain native hysteretic SW state, then model the
* vendor COMPHYS_BASIC_GEN 1-ohm/5-nF output pole before combining states.
.subckt AUTH_UCC27511A_HS INM INP VDD GND OUT
Vlogic logic_ref GND 1
.model SW_PWM_H SW(Ron=1 Roff=1e9 Vt=1.7 Vh=.5)
.model SW_INM_H SW(Ron=1 Roff=1e9 Vt=1.7 Vh=.5)
.model SW_AUX_H SW(Ron=1 Roff=1e9 Vt=4.05 Vh=.15)
Rinm_pull INM VDD 200k
Rinp_pull INP GND 230k
Spwm_state logic_ref pwm_state INP GND SW_PWM_H
Rpwm_state pwm_state GND 100k
Sinm_state logic_ref inm_state INM GND SW_INM_H
Rinm_state inm_state GND 100k
Saux_state logic_ref aux_state VDD GND SW_AUX_H
Raux_state aux_state GND 100k
.param STATE_LO=9.99900009999e-5 STATE_HI=0.9999900001
Bpwm_raw pwm_logic_raw GND V=min(max((V(pwm_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
Binm_raw inm_logic_raw GND V=min(max((V(inm_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
Baux_raw aux_logic_raw GND V=min(max((V(aux_state,GND)-STATE_LO)/(STATE_HI-STATE_LO),0),1)
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
.ends AUTH_UCC27511A_HS
