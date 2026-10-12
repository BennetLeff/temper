#ifndef TEMPER_TANK_FREQ_H
#define TEMPER_TANK_FREQ_H
/*
 * Native-21 tank ceiling, the trips derived from it, and the per-pan frequency loop
 * (power-stage DECISIONS.md item 10; stage-15 PLAN section 4). Pure functions, no HAL: the binding
 * (n21_binding.c) calls tank_freq_step() once per closed half line cycle while the bridge runs.
 *
 * Ceiling. The commissioned tank RMS ceiling is a configuration value: 22 A ships, the hardware is
 * sized for 28 A (stage 15), and it is raised 22 -> 24 -> 26 -> 28 A only through the bench gates in
 * COMMISSIONING.md "Raising the commissioned tank ceiling". Everything else derives from it:
 *   peak trip   = min(2.17 x ceiling + 3, 62) A   (2.17 = round 6's largest peak / line RMS; 3 A pickup)
 *   RMS trip    = 1.05 x ceiling on the half-cycle RMS from input_limits_half_cycle()
 *   crest guard = 1.5 x ceiling on each AD8436 sample (crest sample ~ 1.41 x line RMS)
 * Note: at 28 A the 62 A cap binds, so the loop's peak limit (62 - 3 A) holds the line RMS to
 * 59 / 2.17 = 27.2 A while the peak estimate is 2.17 x RMS (bench calibration of the peak ratio
 * releases it).
 *
 * Loop (round 6 "firmware frequency rule"). Approach from f_max (60 kHz) downwards and stop at the
 * lowest f that keeps all of:
 *   f >= max(f_min (35 kHz), 1.05 x f_res)  -- see "ZVS" below
 *   half-cycle tank RMS <= effective ceiling (no-pan clamp below)
 *   inlet bound <= inlet hold (adapter inlet_target_a: 11.1 A power-stage share at e_est 10 %)
 *   tank peak estimate <= peak trip - 3 A
 * Above resonance P and I fall monotonically with f, so the lowest such f is the maximum-power
 * point. Each half: step down by step_down_hz if every limit holds with `hyst` to spare; hold inside
 * a hysteresis band or at the floor; step up if a limit is exceeded, f is below the floor, or any
 * input is missing (invalid half, no CT_ZC lag). A limit exceeded by more than `hyst` retreats
 * step_up_hz, a marginal excess step_down_hz; either way the frequency that exceeded it is not
 * re-approached for block_halves (one 250 Hz step can move a low-R pan's current by more than the
 * band; without the block the loop limit-cycles). Steps are taken from the frequency that was live
 * at the end of the half, so a lagging actuator cannot wind the target up.
 *
 * ZVS. Two conditions, both required to step down:
 *  (a) measured lag >= zvs_lag_deg (45 deg). For a series RLC, tan(phi) = Q (f/f0 - f0/f), so
 *      phi >= 45 deg proves f >= 1.05 f_res for any loaded Q <= 10 (10 x (1.05 - 1/1.05) = 0.976).
 *      Loads with Q > 10 are the empty or weakly coupled coil, whose f_res (<= 28.4 kHz at 70 uH /
 *      0.45 uF) is below f_min / 1.05. Round 6: every grid operating point has phi >= 50 deg. The lag
 *      is measured to one capture tick (0.27 deg at 60 kHz), so (a) is well conditioned everywhere.
 *  (b) f >= 1.05 x f_res once f_res is estimated. Series-RLC first harmonic:
 *      tan(phi) = (L/R)(w - w0^2/w). Two lags at frequencies at least fit_sep_hz apart give w0^2 and
 *      L/R in closed form; C cancels, so no bank tolerance enters. Only lags <= fit_lag_max_deg (80)
 *      are used: near 90 deg one capture tick moves tan(phi) as much as a 2 kHz step does. Between
 *      fits, w0 follows each half's lag with the last L/R; a lag the last L/R cannot explain
 *      (tan(phi) >= w L/R) discards the fit.
 * n21_cos_phi()'s min_lag latch (5 deg) stays the hard ZVS backstop underneath.
 *
 * No-pan clamp (enclosure ferrite study: 28 A with no pan drives the N87 bars to ~205 / 264 mT and
 * 5.4-7.7 W core loss). Until a pan is established the effective ceiling is
 * min(ceiling, TANK_CEILING_DEFAULT_A). A pan is established after pan_confirm_halves consecutive
 * halves that each show: a valid f_res estimate, a lag <= fit_lag_max_deg, loaded Q = w0 L/R <=
 * pan_q_max, half-cycle RMS >= pan_min_rms_a, and delivered power per amp squared
 * p_inv / I_rms^2 >= pan_r_min_ohm. Any half without that evidence, or any invalid half, drops it at
 * once (fail safe to the lower limit). Both criteria are bench-tunable ESTIMATES (empty coil:
 * R ~ 0.12-0.25 ohm, Q ~ 50-100, lag ~ 88 deg; a pan that needs 28 A for the 1239 W hold:
 * R ~ 1.4 ohm, Q ~ 4-8).
 * Power request. The user's setting (adapter requested_w, input-side watts) is the fifth limit,
 * the softest: the loop targets input power = min(request, the limit-bound maximum). It stops
 * stepping down once input power reaches (1 - power_band) x request and steps up when it exceeds
 * (1 + power_band) x request (marginal retreat + block, as for any limit). Power goes as I^2, so
 * one 250 Hz step moves it by up to ~5.7 % on a low-R pan near the floor (2.8 % in current); the
 * dead band (2 x 6 % = 12 %) is wider than one step, so the loop cannot jump across it and chatter.
 * A request raised by more than the band clears the re-approach block. Every other limit wins over
 * the request. A request below what the pan draws at f_max cannot be met continuously: the loop
 * holds f_max (TF_POWER_AT_FMAX) and delivers that minimum (pulse-skipping / burst is not
 * implemented). A request of 0 stops the bridge in the adapter (gate off, loop reset).
 * Regulation overrun: more than overrun_halves consecutive halves above 1.05 x the effective
 * ceiling returns TF_FAULT_OVERRUN, which the binding latches as N21_FAULT_TANK_RMS.
 */
#include <stdbool.h>
#include <stdint.h>

#define TANK_CEILING_DEFAULT_A 22.0f /* shipping commissioned ceiling; also the no-pan clamp */
#define TANK_CEILING_MAX_A     28.0f /* stage-15 hardware sizing basis (DECISIONS 10) */
#define TANK_CEILING_MIN_A     10.0f
#define TANK_PEAK_PER_RMS      2.17f /* round 6 board-side-protection.csv, 22 A row */
#define TANK_PEAK_PICKUP_A     3.0f
#define TANK_PEAK_TRIP_CAP_A   62.0f
/* config cap: below the stage-15 CT band low corner (64.55 A), so the firmware trip stays under
 * the hardware trip. CT_MON range is 80 A (62 A -> 2.58 V < 2.85 V). */
#define TANK_PEAK_TRIP_MAX_A   64.5f
#define TANK_RMS_TRIP_RATIO    1.05f
#define TANK_CREST_GUARD_RATIO 1.5f
/* Peak estimate from the AD8436 per-sample envelope: sqrt(2) x crest RMS sample x 1.05, until
 * bench calibration (PLAN section 4). */
#define TANK_PEAK_PER_CREST_RMS (1.41421356f * 1.05f)

/* Stuck-low plausibility of the AD8436 tank-RMS channel (n21_binding.c, evidence
 * build-evidence/rms-estimator). The CT_MON sample peak cannot exceed the half-cycle RMS by more
 * than the firmware's own crest bound TANK_PEAK_PER_RMS (2.17: round 6, 13 configs at 22 A, the
 * same ratio that sets the peak trip and the peak estimate) times a margin of 1.20, so the latch
 * threshold is 2.17 x 1.20 = 2.60. The margin is wide on purpose: at the ADC phase-lock frequencies
 * (40 kHz and k x 8.889 kHz, e.g. 53.33 kHz) the CT_MON samples land on the same tank phases every
 * half, and if those phases are near the crest max|CT_MON| equals the true crest in all
 * TANK_RMS_PLAUS_HALVES halves in a row. The study's synthetic crest is 2.30 at 50-55 kHz, which a
 * 5 % margin (2.28) would nuisance-latch. The check only has to catch gross failures (stuck at 0, a
 * half-scale reading: ratio 4 or more); 2.60 does, with a wide margin. A reading below
 * max|CT_MON| / (1.20 x 2.17) is impossible for a working channel.
 * It is only judged while the bridge runs and the tank current is clearly above the CT_MON noise
 * and offset floor (TANK_RMS_PLAUS_MIN_CT_A: > 3 x cos_phi_min_current_a), and only fires after
 * TANK_RMS_PLAUS_HALVES consecutive implausible halves: burst edges (a half that starts or ends
 * the bridge, the converter still settling) are single halves between plausible or idle ones. */
#define TANK_RMS_PLAUS_MARGIN    1.20f
#define TANK_RMS_PLAUS_MIN_CT_A  6.0f
#define TANK_RMS_PLAUS_HALVES    6u /* 50 ms; the 100 ms overrun latch is 12 halves */
bool tank_rms_implausible(float half_rms_a, float ct_abs_max_a);

float tank_peak_trip_for(float ceiling_a);
float tank_rms_trip_for(float ceiling_a);
float tank_crest_guard_for(float ceiling_a);
bool tank_ceiling_ok(float ceiling_a); /* finite, TANK_CEILING_MIN_A..TANK_CEILING_MAX_A */

typedef struct {
    uint32_t f_min_hz, f_max_hz;  /* 35000 / 60000; bridge_plan_cycle's window */
    uint32_t step_down_hz;        /* approach step per closed half, 50..1000 */
    uint32_t step_up_hz;          /* retreat step per closed half, step_down..2000 */
    uint32_t fit_sep_hz;          /* min spacing of the two lags in an f_res fit */
    float f_res_margin;           /* >= 1.05 */
    float zvs_lag_deg;            /* (a): lag needed to step down, 45 */
    float fit_lag_max_deg;        /* lags above this do not feed the f_res fit, 80 */
    float hyst;                   /* relative hold band at each limit */
    float peak_margin_a;          /* >= 3 A coil pickup */
    float pan_q_max, pan_r_min_ohm, pan_min_rms_a;
    uint32_t pan_confirm_halves, overrun_halves;
    uint32_t block_halves;        /* re-approach lock-out after a limit was exceeded */
    float power_band;             /* relative half-width of the power dead band, 0.03..0.2 */
} tank_freq_cfg_t;

typedef struct {
    float ceiling_a;   /* commissioned tank RMS ceiling */
    float inlet_max_a; /* hold on est.inlet_bound_a (adapter inlet_target_a) */
    float peak_trip_a; /* firmware peak trip */
    float request_w;   /* requested input power (adapter requested_w); <= 0 retreats */
} tank_freq_limits_t;

typedef struct {
    bool valid;        /* a complete half cycle with fresh samples */
    bool phase_valid;  /* CT_ZC lag measured over it */
    bool fit_ok;       /* frequency spread over the half <= one approach step: may feed the fit */
    uint32_t f_hz;     /* frequency live at the end of the half (the step basis) */
    float f_fit_hz;    /* mean frequency over the half (the fit's abscissa) */
    float phi_rad;     /* mean lag of the tank current behind the bridge voltage */
    float tank_rms_a, inlet_a, peak_a, p_inv_w;
    float p_in_w;      /* input-side power estimate (input_limits p_in_w) */
} tank_freq_obs_t;

typedef enum {
    TF_DOWN = 0,
    TF_HOLD_LIMIT,     /* inside the hysteresis band of a limit, or re-approach blocked */
    TF_HOLD_FLOOR_MIN, /* at f_min */
    TF_HOLD_FLOOR_ZVS, /* at 1.05 f_res */
    TF_UP_INVALID,     /* invalid / stale half */
    TF_UP_NO_PHASE,    /* no CT_ZC lag */
    TF_UP_BELOW_FLOOR, /* below 1.05 f_res */
    TF_UP_LAG,         /* lag below zvs_lag_deg */
    TF_UP_RMS,
    TF_UP_INLET,
    TF_UP_PEAK,
    TF_UP_POWER,       /* input power above (1 + power_band) x request */
    TF_HOLD_POWER,     /* input power inside the request's dead band */
    TF_POWER_AT_FMAX,  /* request below the f_max minimum: capped at f_max */
    TF_FAULT_OVERRUN,  /* effective ceiling exceeded for too long: latch */
} tank_freq_reason_t;

typedef struct {
    uint32_t f_hz;            /* target */
    uint32_t floor_hz;
    bool have_anchor, have_fit, pan_present;
    float anchor_hz, anchor_tan;
    float l_over_r_s;         /* L/R from the last two-point fit */
    float f_res_hz, q;        /* current estimate */
    float ceiling_eff_a;
    uint32_t pan_count, overrun;
    uint32_t block_hz, block_left; /* no step down to <= block_hz while block_left > 0 */
    float last_request_w;
    tank_freq_reason_t reason;
} tank_freq_t;

tank_freq_cfg_t tank_freq_default(void);
bool tank_freq_config_ok(const tank_freq_cfg_t *);
/* Back to f_max; forgets the fit, the pan and any block (call whenever the bridge is not running). */
void tank_freq_reset(tank_freq_t *, const tank_freq_cfg_t *);
tank_freq_reason_t tank_freq_step(tank_freq_t *, const tank_freq_cfg_t *, const tank_freq_limits_t *,
                                  const tank_freq_obs_t *);
/* Two-point series-RLC fit. Both lags inductive (tan > 0), tan(phi) * w increasing with w, and the
 * resonance below both points; otherwise false. */
bool tank_freq_fit(float f1_hz, float tan1, float f2_hz, float tan2, float *w0sq, float *l_over_r_s);
/* Move `from` towards `to` by at most max_step. */
uint32_t tank_freq_slew(uint32_t from, uint32_t to, uint32_t max_step);
#endif
