#ifndef TEMPER_BLOWER_AUX_H
#define TEMPER_BLOWER_AUX_H
/*
 * Inlet allowance for the blower supply PS3, scheduled with the blower drive (power-stage
 * DECISIONS 16; stage-16 PLAN section 5, budget16.py). Pure functions, no HAL; host-tested by
 * firmware/test/test_blower_aux.c.
 *
 * Stage 16 moves the blower off PS1 onto its own module, PS3 (Mean Well IRM-60-15ST, mains tap
 * F2 / J11), so the inlet carries three modules. The firmware inlet estimate (input_limits.h)
 * adds an auxiliary allowance to the power-stage estimate and regulates the total to 13.5 A:
 *   I_aux = PS1 + PS2 (static, the existing 1.3 A basis) + PS3(drive).
 * A static PS3 at full blower (I_aux 2.57 A) holds the power stage at 9.94 A, -127 W against the
 * 1239 W hold. Scheduling PS3 with the drive the fan law actually commands returns most of that
 * whenever the blower runs below full speed.
 *
 * PS3(drive) model, conservative at every step (all values PROVISIONAL until COMMISSIONING.md
 * step 8c measures PS3's input current against the drive and replaces them):
 *   1. Drive -> blower voltage: the C28 buck with GPIO46 injection, duty 0 = full speed.
 *      V(duty) <= vout_max_v - vout_slope_min_v * duty, the upper envelope over every VFB,
 *      resistor and v3v3 corner (12.40 V at duty 0, 6.81 V at the 0.85 duty cap).
 *   2. Blower power: fan law P = p_rated_max_w * (V / v_rated_v)^fan_law_exp, anchored on the
 *      Delta BFB1012VH-F00's MAXIMUM 32.4 W at 12 V (spec p.1, enclosure R33 study 10; typical
 *      is 17.0 W), so 35.7 W at the 12.40 V corner.
 *   3. PS3 output = P / eta_buck (TPS62933, 0.90, controller C28 / controller_calcs.json).
 *   4. PS3 input current at the low-line corner: P_out / (ps3_eta * ps3_pf * v_line_low_v), with
 *      ps3_eta = 89 % (IRM-60-15 typ., IRM-60-SPEC 2025-11-21 p.2) and the capacitor-input power
 *      factor implied by the same page's AC current, 1.8 A typ. at 115 Vac full load:
 *      PF = (60 W / 0.89) / (115 V * 1.8 A) = 0.326. At full blower this is 1.27 A, the
 *      budget16.py basis; total worst case 1.3 + 1.27 = 2.57 A.
 *   5. Margin below full speed: (1 + margin) on the modelled current plus idle_a (PS3 no-load and
 *      X-capacitor current; < 0.15 W no-load, p.1) - light-load efficiency and power factor are
 *      worse than the full-load figures above - capped at the worst case.
 *   The worst case (no margin: it already stacks the blower's maximum power, the buck's high
 *   voltage corner and the low line) is used whenever the drive is unknown: at boot, after a
 *   failed blower write, with the blower faulted (stall), at full speed (duty 0, the fan law's
 *   fault output), and with the blower commanded off but still turning (FAN_OFF not confirmed
 *   by the tach).
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
    float base_a;              /* PS1 + PS2 static allowance (input_limits aux_min_a), A */
    /* drive -> blower voltage (C28 buck, upper envelope) */
    float vout_max_v;          /* at duty 0 */
    float vout_slope_min_v;    /* minimum dV / d(duty) over the corners */
    /* blower */
    float v_rated_v, p_rated_max_w, fan_law_exp;
    float eta_buck;
    /* PS3 */
    float ps3_eta, ps3_pf, v_line_low_v;
    float idle_a;              /* PS3 input with the blower off (FAN_OFF) or added below full speed */
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
float blower_aux_worst_a(const blower_aux_cfg_t *);                  /* PS1 + PS2 + PS3 full */
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
