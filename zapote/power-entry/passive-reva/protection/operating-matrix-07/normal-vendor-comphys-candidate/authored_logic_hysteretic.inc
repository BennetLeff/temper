* Diagnostic hybrid: TI COMPHYS input-state front end plus authored output.
* The COMPHYS primitive is copied verbatim from the local TI UCC27511A model.
* COMPHYS OUT is a hard behavioral state; its internal R1/C1 node is not
* filtered externally. The Bdriver_req/product and output pole remain authored.
.SUBCKT COMPHYS_BASIC_GEN INP INM HYS OUT PARAMS: VDD=1 VSS=0 VTHRESH=0.5	
EIN INP1 INM1 INP INM 1 
EHYS INP1 INP2 VALUE { IF( V(1) > {VTHRESH},-V(HYS),0) }
EOUT OUT 0 VALUE { IF( V(INP2)>V(INM1), {VDD} ,{VSS}) }
R1 OUT 1 1
C1 1 0 5.0n
RINP1 INP1 0 1K
.ENDS COMPHYS_BASIC_GEN

.subckt AUTH_UCC27511A_H INM INP VDD GND OUT
* Exact TI input connections (UCC27511A.lib lines 79--95):
* PWM/INM use 2.2 V with 1 V HYS; AUX uses 4.2 V with 0.3 V HYS.
V_pwm_threshold pwm_threshold GND 2.2
V_pwm_hys pwm_hys GND 1
X_pwm INP pwm_threshold pwm_hys pwm_state COMPHYS_BASIC_GEN
V_inm_threshold inm_threshold GND 2.2
V_inm_hys inm_hys GND 1
X_inm INM inm_threshold inm_hys inm_state COMPHYS_BASIC_GEN
V_aux_threshold aux_threshold GND 4.2
V_aux_hys aux_hys GND 0.3
X_aux VDD aux_threshold aux_hys aux_state COMPHYS_BASIC_GEN
* Retain exact TI nominal input loading (UCC27511A.lib lines 87--88).
Rinm_pull INM VDD 200k
Rinp_pull GND INP 230k
* Authored output surrogate retained intentionally: product logic, 18.75 nF
* delay pole, and 1 ohm output resistance are not the TI output stage.
Bdriver_req driver_req GND V=V(VDD,GND)*V(pwm_state,GND)*(1-V(inm_state,GND))*V(aux_state,GND)
Rdriver_delay driver_req drv_delay 1
Cdriver_delay drv_delay GND 18.75n
Routput drv_delay OUT 1
.ends AUTH_UCC27511A_H
