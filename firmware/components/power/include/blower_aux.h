#ifndef TEMPER_BLOWER_AUX_H
#define TEMPER_BLOWER_AUX_H
/*
 * Inlet allowance for the auxiliary supplies PS2 + PS3, scheduled with the blower drive (power-stage
 * DECISIONS 16; stage-16 PLAN section 5, budget16.py). Pure functions, no HAL; host-tested by
 * firmware/test/test_blower_aux.c.
 *
 * The inlet feeds two modules since s38 (PS1 deleted): PS2 (Mean Well MPM-20-24, HOT side, gate
 * bias + HOT5) and PS3 (MPM-65-15ST, mains tap F2 / J11: the controller logic through the J13 merge
 * plus the blower buck). The firmware inlet estimate (input_limits.h) adds an auxiliary allowance
 * to the power-stage estimate and regulates the total to 13.5 A:
 *   I_aux = base (PS2 + PS3 logic, static) + PS3 blower(drive).
 * The allowance is each module's INCREMENT to the inlet RMS at the hold point, RMS(i_ps + i_aux) -
 * RMS(i_ps), not the linear sum of datasheet AC currents: the power stage draws a near-sinusoidal
 * in-phase current, so the auxiliaries add mostly their real-power current P_in / V plus a
 * harmonic term (temper-aux-load-r1, aux_load.py -> aux-load.json, the single source of the
 * numbers below). At full blower the static worst case is 0.887 A, holding the power stage at
 * 11.47 A (it was 2.57 A / 9.94 A on the IRM-20 + IRM-60 linear-sum basis).
 *
 * Model, conservative at every step (all values PROVISIONAL until COMMISSIONING.md step 8c measures
 * the inlet true-RMS current against the drive and replaces them):
 *   0. base_a: the worst-corner increment with the blower off, 0.2538 A, rounded up to 0.26 A.
 *      Worst corner: 108 V; PS2 at the 80 kHz bias allocation (11.6 W); logic 4.83 W (every part at
 *      datasheet maximum); efficiency typ. - 5 points; each module's harmonics inflated until its
 *      full-load RMS equals the datasheet AC current (MPM-20-SPEC / MPM-65-SPEC 2024-10-30 p.2:
 *      0.75 A / 1.5 A typ. at 115 Vac); the power-stage current with 20 % 3rd harmonic, worst sign.
 *   1. Drive -> blower voltage: the C28 buck with GPIO46 injection, duty 0 = full speed.
 *      V(duty) <= vout_max_v - vout_slope_min_v * duty, the upper envelope over every VFB,
 *      resistor and v3v3 corner (12.40 V at duty 0, 6.81 V at the 0.85 duty cap).
 *   2. Blower power: fan law P = p_rated_max_w * (V / v_rated_v)^fan_law_exp, anchored on the
 *      Delta BFB1012VH-F00's MAXIMUM 32.4 W at 12 V (spec p.1, enclosure R33 study 10; typical
 *      is 17.0 W), so 35.7 W at the 12.40 V corner.
 *   3. PS3 output added by the blower = P / eta_buck (TPS62933, 0.90, controller C28).
 *   4. Inlet increment above base at the low-line corner: P_out / (ps3_eta * ps3_pf * v_line_low_v),
 *      ps3_eta = 87.5 % (MPM-65 92.5 % typ., MPM-65-SPEC 2024-10-30 p.2, less 5 points: no minimum
 *      is published) and ps3_pf = 0.67, the effective power factor of the increment (real-power
 *      current over increment above base at the same worst corner). It falls with load, so the
 *      lowest value over duty 0..1 and 108 / 120 / 132 V (0.676, at full blower) is used, rounded
 *      down: the unmargined model alone is >= the worst-corner increment at every duty (by >= 5 mA;
 *      test_blower_aux.c pins the aux-load.json vectors). Full blower: 0.627 A; worst case
 *      0.26 + 0.627 = 0.887 A against 0.882 A modelled.
 *   5. Margin below full speed: (1 + margin) on the modelled current plus idle_a (PS3 X-capacitor
 *      and light-load spread), capped at the worst case.
 *   The worst case (no margin: it already stacks the blower's maximum power, the buck's high
 *   voltage corner, the low line and the worst module corner) is used whenever the drive is
 *   unknown: at boot, after a failed blower write, with the blower faulted (stall), at full speed
 *   (duty 0, the fan law's fault output), and with the blower commanded off but still turning
 *   (FAN_OFF not confirmed by the tach).
 *
 * Schedule (blower_aux_step(), once per blower tick, between blower_ctrl and the hardware):
 *   - Speed-up: allowance first. The allowance rises at rise_a_per_s towards the level of the
 *     commanded drive; the blower keeps its previous (slower) drive until that level has been in
 *     force for lead_ms. The binding ramps the allowance it uses by at most aux_slew_a per half
 *     line cycle (n21_binding.h), and the frequency loop backs the power stage off as the bound
 *     rises, so the fan never draws more than the allowance in force and the inlet bound never
 *     steps towards the adapter's 15 A trip.
 *   - Fault path (urgent: any fault, invalid sensor, unknown drive): the blower goes to the
 *     commanded speed at once (thermal safety wins) and the allowance rises at urgent_a_per_s.
 *   - Slow-down: the blower slows at once; the allowance is released after release_ms (the
 *     blower and buck have spun down) at fall_a_per_s.
 */
/*
 * BLW_PG (controller C33, expander P16: PS3 output present) deliberately does NOT enter this
 * schedule. With BLW_PG = 0 the allowance is NOT reduced: PS3's AC side may still draw (a failed
 * output, a tripped OCP / OVP hiccup, a blown output fuse) and BLW_PG itself can be wrong (the
 * firmware's plausibility check against the tach catches that only while the blower turns). A
 * "PS3 absent" stall reaches this module as known = false, i.e. the worst case. Conservative by
 * design: the inlet estimate never relies on PS3 being off.
 */
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    float base_a;              /* PS2 + PS3 logic static allowance (input_limits aux_min_a), A */
    /* drive -> blower voltage (C28 buck, upper envelope) */
    float vout_max_v;          /* at duty 0 */
    float vout_slope_min_v;    /* minimum dV / d(duty) over the corners */
    /* blower */
    float v_rated_v, p_rated_max_w, fan_law_exp;
    float eta_buck;
    /* PS3 */
    float ps3_eta, ps3_pf, v_line_low_v; /* ps3_pf: effective PF of the inlet-RMS increment */
    float idle_a;              /* added with the blower off (FAN_OFF) and below full speed */
    float margin;              /* relative, below full speed */
    /* schedule */
    float rise_a_per_s, urgent_a_per_s, fall_a_per_s;
    uint32_t lead_ms, release_ms;
    float off_rpm;             /* tach below this confirms the blower is off */
} blower_aux_cfg_t;

blower_aux_cfg_t blower_aux_native21(void);
bool blower_aux_config_ok(const blower_aux_cfg_t *);

/* Model pieces (exposed for the tests and telemetry). */
float blower_aux_vout_max_v(const blower_aux_cfg_t *, float duty);  /* NaN / < 0 duty: full */
float blower_aux_ps3_model_a(const blower_aux_cfg_t *, float vout_v); /* unmargined */
float blower_aux_worst_a(const blower_aux_cfg_t *);                  /* base + PS3 blower full */
/* Total allowance for a blower state: off -> base + idle; on -> base + PS3(duty) with margin,
 * capped at the worst case; duty 0 (full speed) or invalid -> the worst case. */
float blower_aux_level_a(const blower_aux_cfg_t *, bool on, float duty);

typedef struct {
    bool on;        /* commanded by blower_ctrl (fan law): buck on (FAN_OFF low) */
    float duty;     /* commanded GPIO46 duty, 0 = full speed */
    bool urgent;    /* fault path: the blower must reach the commanded speed now */
    bool known;     /* the last blower write took effect and the blower is not faulted (stall) */
    float tach_rpm; /* NaN: no reading */
} blower_aux_in_t;

typedef struct {
    bool on;            /* to apply: FAN_OFF = !on */
    float duty;         /* to apply: GPIO46 duty */
    float allowance_a;  /* to n21_set_aux_allowance() */
    float target_a;     /* level the allowance is moving to */
    bool holding;       /* a speed-up is waiting for its allowance */
} blower_aux_out_t;

typedef struct {
    bool primed;
    uint32_t last_ms;
    uint32_t rise_ms;     /* last time the allowance rose */
    float allowance_a;
    bool on;              /* applied */
    float duty;
    bool lower;
    uint32_t lower_since_ms;
} blower_aux_t;

/* Starts at the worst case with the blower at its reset state (on, near full speed). */
void blower_aux_init(blower_aux_t *, const blower_aux_cfg_t *);
blower_aux_out_t blower_aux_step(blower_aux_t *, const blower_aux_cfg_t *, const blower_aux_in_t *,
                                 uint32_t now_ms);
#endif
