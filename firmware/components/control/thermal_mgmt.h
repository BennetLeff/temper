#ifndef TEMPER_THERMAL_MGMT_H
#define TEMPER_THERMAL_MGMT_H
/*
 * Thermal management for the integrated controller (pure C, host-tested by
 * firmware/test/test_thermal_mgmt.c). Hardware source of truth: branch controller-layout,
 * zapote/controller DECISIONS C28 (blower), C29 (NTC input RC), C31 (rim NTC), C32 (trip ladder),
 * tools/controller_calcs.py and docs/evidence/2026-10-12-thermal-trip-ladder-l3.md.
 *
 *  - NTC divider conversion for the controller's NTC channels (heatsink, coil, rim), each with
 *    its sensor tolerance, its input RC (C29) and the ESP32-S3 ADC's measurable range.
 *  - The L3 trip ladder (C32): fan-law point < firmware derate < firmware hard trip < hardware
 *    comparator trip (the independent backstop), for the heatsink and the coil.
 *  - Pan temperature cap, 250 C (owner 2026-10-09, R32 CONTROLLER-SPEC): a power cap from the pan
 *    RTD and, independently and more slowly, from the rim NTC (R36 DECISIONS 4).
 *  - Fan law (R32): drive = max(sink loop, coil loop); PI on the heatsink NTC at 88.6 C and on the
 *    coil NTC at 140 C; off below 50 C with 5 K hysteresis; drive cap 0.8 except in a fault (then
 *    full speed); coil above 150 C (the mean winding limit) derates tank power, at any fan drive.
 *  - Blower (C28): inverted PWM map (duty 0 = full speed), FG tach to rpm, stall detection (tach
 *    below threshold for > 1 s while driven derates tank power at once, and stops it if the sink
 *    or coil keeps rising), and blower_ctrl_step(), the whole per-tick decision the ESP glue runs.
 *  - Blower supply (C33): BLW_PG (PS3 present) splits a stall into "PS3 absent" and "blower
 *    failed", blocks a heating start while PS3 is absent, and is checked against the tach.
 *
 * Values marked PROVISIONAL have no measured basis yet and must be set on the bench.
 */
#include <stdbool.h>
#include <stdint.h>

/* ---------------------------------------------------------------- NTC models */
/* Vishay extended Steinhart-Hart material constants (R/R25 = exp(A + B/T + C/T^2 + D/T^3), and the
 * inverse 1/T = A1 + B1 ln(R/R25) + C1 ln^2 + D1 ln^3, T in K). */
typedef struct {
    double a, b, c, d;     /* R(T) */
    double a1, b1, c1, d1; /* T(R) */
} ntc_curve_t;

/* Vishay "Mat. D", curve 11, B25/85 = 4190 K +/- 1.5 %: Vishay NTCLE100E3 data sheet (doc 29049,
 * rev. 07-May-2025), page 4, "Parameter for determining nominal resistance values". The
 * NTCALUG01A104GA (doc 29092, rev. 14-Jan-2026, page 2 ordering table: 100 kOhm +/- 2 %, B25/85
 * 4190 K +/- 1.5 %) gives no R-T table of its own and points to Vishay's curve computation; the
 * 100 k / 4190 K +/- 1.5 % curve is this material. Its R-T values at 25/100/140/150 C (doc 29049
 * page 12, NTCLE100E3104: 100.0 / 5.835 / 1.854 / 1.434 kOhm) are pinned in test_thermal_mgmt.c. */
extern const ntc_curve_t NTC_CURVE_VISHAY_MAT_D_4190;

/* Manufacturer R-T table. Between points ln(R) is interpolated linearly in 1/T (exact for a part
 * whose B is constant over the interval); outside the table the end interval's B extrapolates. */
typedef struct {
    unsigned n;
    const float *t_c;   /* ascending */
    const float *r_ohm; /* at the table's own R25 (r25_ref_ohm); scaled by the channel's r25_ohm */
    float r25_ref_ohm;
} ntc_table_t;

/* Semitec 104GT-2 (GT-2 series data sheet, semitec.co.jp "GT-2シリーズ.pdf", 2023-08-01, p. 18):
 * 100 kOhm +/- 3 % at 25 C, B25/85 4267 K +/- 2 %, -50..+300 C, dissipation constant ~0.6 mW/C,
 * thermal time constant ~7 s (still air), rated power 3 mW. Table points are the ones transcribed
 * on controller-layout zapote/controller/tools/controller_calcs.py (GT2_104, GT2_104_HOT), plus
 * 85 C from the B25/85 definition (R85 = R25 exp(-B (1/298.15 - 1/358.15)) = 9.094 k). The
 * 30..85..100 C gap is interpolated; its error is <= 0.5 K and no trip sits in it. */
extern const ntc_table_t NTC_TABLE_SEMITEC_104GT2;

/* ESP32-S3 ADC1 at 12 dB attenuation measures 0..~3100 mV (ESP-IDF v5.2 ADC guide, ESP32-S3
 * "ADC_ATTEN_DB_12 ... 0 mV ~ 3100 mV"). A node above this reads as the top of the range. */
#define THERMAL_ADC_MEAS_MAX_MV 3100.0f

typedef struct ntc_channel {
    float r_pullup_ohm;         /* to v_ref */
    float r25_ohm;              /* NTC at 25 C */
    float beta_k;               /* B25/85: the model when curve and table are NULL, and the
                                 * tolerance basis */
    const ntc_curve_t *curve;   /* Vishay R-T model, or NULL */
    const ntc_table_t *table;   /* manufacturer table, or NULL */
    float v_ref_mv;             /* divider supply (v3v3, C8: 3.304 V nominal) */
    float t_open_c;             /* a node implying colder than this = open NTC / unplugged */
    float t_short_c;            /* a node implying hotter than this = shorted NTC */
    float v_meas_max_mv;        /* ADC top: a node above it is NTC_BELOW_RANGE (cold, or open) */
    float r25_tol, beta_tol;    /* sensor tolerance (fractions) for ntc_channel_tol_k() */
    float dissipation_mw_per_k; /* sensor dissipation constant, for ntc_channel_self_heat_k() */
    /* C29 input filter ahead of the buffer: series R into C, after the node's own capacitance
     * (HS / COIL: the thermal-sense block's 100 nF at the node; RIM: none, TVS only). */
    float filt_r_ohm, filt_c_f, node_c_f;
} ntc_channel_t;

/* Rim NTC (C31): Semitec 104GT-2 on a 1.00 k 0.1 % pull-up (RT0603BRD071KL). At 250 C the node is
 * 0.489 V with 7.0 mV/K. The macros are the drop-in point for a part change; the 104GT-2
 * table (scaled to RIM_NTC_R25_OHM) is used unless RIM_NTC_USE_GT2_TABLE is 0 (beta model).
 *
 * Self-heating (documented, deliberately not corrected): the NTC dissipates V^2 R / (R + R_pu)^2,
 * 1.38 mW at 250 C (3.304 V, 174 Ohm, 1.00 k), i.e. ~2.3 K high in still air at 0.6 mW/K
 * (controller_calcs.py rim_ntc(): 2.3 K; from the transcribed R-T table, superseding an earlier
 * B-model estimate of 1.6 mW / ~2.6 K); peak 2.7 mW at R = R_pu (~157 C). It reads hot, which brings the 250 C cap in earlier:
 * the safe side. Mounted on the glass in the R36 rim boss it is lower than in still air. */
#ifndef RIM_NTC_R_PULLUP_OHM
#define RIM_NTC_R_PULLUP_OHM   1000.0f
#endif
#ifndef RIM_NTC_R25_OHM
#define RIM_NTC_R25_OHM      100000.0f
#endif
#ifndef RIM_NTC_BETA_K
#define RIM_NTC_BETA_K         4267.0f
#endif
#ifndef RIM_NTC_USE_GT2_TABLE
#define RIM_NTC_USE_GT2_TABLE  1 /* 0: beta model from RIM_NTC_R25_OHM / RIM_NTC_BETA_K */
#endif
extern const ntc_channel_t THERMAL_NTC_RIM;
/* Heatsink: Vishay NTCALUG01A104GA on a 10.0 k pull-up (thermal-sense block), unchanged at L3. */
extern const ntc_channel_t THERMAL_NTC_SINK;
/* Coil (C32): Semitec 104GT-2 class, 100 k / 300 C glass NTC, on the same 10.0 k pull-up. The lug
 * NTC's 150 C rating does not cover the coil band. Self-heating ~0.08 mW at 170 C: negligible. */
extern const ntc_channel_t THERMAL_NTC_COIL;

typedef enum {
    NTC_OK = 0,
    NTC_OPEN,
    NTC_SHORT,
    NTC_BAD_ARG,
    /* Node above the ADC's measurable range: the sensor is colder than ntc_channel_range_min_c(),
     * or open. *temp_c is set to that floor (an upper bound for a healthy sensor). HS and COIL
     * opens are caught by the thermal-sense block's OPEN_REF comparator (hardware latch); the rim
     * has no hardware open detect, so its consumers treat this as "no rim reading". */
    NTC_BELOW_RANGE,
} ntc_status_t;

/* NTC resistance at a temperature, and the inverse, through the channel's model. */
float ntc_channel_r_at(const ntc_channel_t *ch, float temp_c);
ntc_status_t ntc_channel_temp_c(const ntc_channel_t *ch, float mv, float *temp_c);
/* Inverse (divider voltage at a temperature): for thresholds and tests. */
float ntc_channel_mv_at(const ntc_channel_t *ch, float temp_c);
/* Lowest temperature the channel can resolve (node = v_meas_max_mv). */
float ntc_channel_range_min_c(const ntc_channel_t *ch);
/* Worst-case reading error (K, one-sided) from the sensor's R25 and B tolerances at temp_c. */
float ntc_channel_tol_k(const ntc_channel_t *ch, float temp_c);
/* Steady self-heating of the NTC at temp_c (K), from the divider current. */
float ntc_channel_self_heat_k(const ntc_channel_t *ch, float temp_c);

/* ---------------------------------------------------------------- input RC (C29) */
/* Component tolerances behind the worst case: 1 % resistors, X7R 100 nF +/- 10 %. */
#define NTC_RC_R_TOL 0.01f
#define NTC_RC_C_TOL 0.10f
/* Worst-case dominant delay (s) of the node + filter, as the sum of open-circuit time constants
 * (Elmore): R_th C_node + (R_th + R_filt) C_filt, R_th = pull-up || NTC <= pull-up. 10 k / 100 nF
 * alone is 1.0 ms (159 Hz); HS / COIL with their node capacitor are <= 3.3 ms, RIM <= 1.2 ms. */
float ntc_input_tau_s(const ntc_channel_t *ch);
/* Settling to 1 LSB of 12 bits from a full-scale step (ln 4096 = 8.3 time constants), ms. */
uint32_t ntc_input_settle_ms(const ntc_channel_t *ch);
/* False until the input has settled after the v3v3 rail came up (the capacitors start at 0 V,
 * which reads as a hot or shorted NTC). Every consumer gates on it. */
bool ntc_input_settled(const ntc_channel_t *ch, uint32_t ms_since_supply_up);
/* Lag of the filtered reading behind a ramp of rate_k_per_s (K): tau * rate. */
float ntc_input_lag_k(const ntc_channel_t *ch, float rate_k_per_s);

/* ---------------------------------------------------------------- trip ladder (C32) */
/* Firmware: the heatsink hard trip is OVER_TEMP_THRESHOLD (firmware/config.yaml, 95 C); the coil's
 * is COIL_FW_TRIP_C below. Hardware: the thermal-sense comparators as fitted on the controller
 * (controller-layout zapote/controller/evidence/verify.json "thermal", controller_calcs.py
 * thermal_trips(): 64 corners = sensor R25/B at their limits x each resistor at its tolerance). */
#define THERMAL_HW_SINK_TRIP_NOM_C    101.4f
#define THERMAL_HW_SINK_TRIP_LOW_C     98.3f
#define THERMAL_HW_SINK_TRIP_HIGH_C   104.6f
#define THERMAL_HW_SINK_REL_LOW_C      83.0f
#define THERMAL_HW_SINK_REL_HIGH_C     88.2f
#define THERMAL_HW_COIL_TRIP_NOM_C    175.7f
#define THERMAL_HW_COIL_TRIP_LOW_C    169.7f
#define THERMAL_HW_COIL_TRIP_HIGH_C   182.0f
#define THERMAL_HW_COIL_REL_LOW_C     147.4f
#define THERMAL_HW_COIL_REL_HIGH_C    157.7f

/* ---------------------------------------------------------------- pan cap */
#define PAN_CAP_C        250.0f /* owner, 2026-10-09 */
#define PAN_CAP_BAND_C    10.0f /* PROVISIONAL: linear derate from 240 C to 0 at 250 C */

typedef struct {
    uint8_t cap_pct;   /* 0..100, applied as min(request, cap) */
    bool rtd_limiting; /* the pan RTD is inside the derate band */
    bool rim_limiting; /* the rim NTC is inside the derate band */
    bool rim_invalid;  /* rim reading unavailable: no rim cap, flagged for the UI / log */
} pan_cap_t;

/* An invalid pan RTD gives cap 0 (the RTD path has its own faults; this only refuses heat). An
 * invalid rim gives no rim cap: it is the backup path, and the RTD still caps. */
pan_cap_t pan_cap_evaluate(float pan_rtd_c, bool rtd_valid, float rim_c, bool rim_valid);

/* ---------------------------------------------------------------- sensor plausibility */
/* The ESP32-S3 ADC cannot see the node near v3v3, so a cold NTC and an open one read alike
 * (NTC_BELOW_RANGE). Coordinator decision 2026-10-12: resolve it in firmware by plausibility,
 * latched until MCU reset; no hardware change. All values PROVISIONAL (bench-tunable).
 *  - Rim: below its range (cold, < ~70 C, or open) while the pan RTD reads > 150 C for > 30 s ->
 *    rim-sensor fault: the rim is dropped from the 250 C cap (pan-RTD-only cap) and the user is
 *    told.
 *  - Coil: below 25 C after > 5 min (cumulative) of heating at > 50 % power -> coil-sensor fault:
 *    the tank is clamped to COIL_SENSOR_FAULT_TANK_MAX_A and the blower runs full speed. A true
 *    open is still latched in hardware by the thermal-sense OPEN_REF comparator. */
#define RIM_PLAUS_PAN_HOT_C          150.0f
#define RIM_PLAUS_TIME_MS            30000u
#define COIL_PLAUS_COLD_C             25.0f
#define COIL_PLAUS_POWER_PCT             50u
#define COIL_PLAUS_TIME_MS          300000u
#define COIL_SENSOR_FAULT_TANK_MAX_A  22.0f
#define THERMAL_PLAUS_MAX_STEP_MS       200u /* a gap between calls (not heating) does not count */

typedef struct {
    bool primed;
    uint32_t last_ms;
    uint32_t rim_ms;  /* continuous time the rim condition has held */
    uint32_t coil_ms; /* cumulative heating time at > 50 % power with the coil reading cold */
    bool rim_fault, coil_fault; /* latched */
} thermal_plaus_t;

void thermal_plaus_init(thermal_plaus_t *p);
/* Call every control tick while heating. rim_cold_or_open: the rim node is NTC_BELOW_RANGE or
 * NTC_OPEN. coil_c: the coil reading (the range floor when below range; NaN is handled by the
 * over-temperature interlock and ignored here). power_pct: the tank power level applied. */
void thermal_plaus_update(thermal_plaus_t *p, uint32_t now_ms, bool rim_cold_or_open,
                          float pan_rtd_c, bool rtd_valid, float coil_c, uint8_t power_pct);

/* ---------------------------------------------------------------- fan law */
#define FAN_SINK_SETPOINT_C     88.6f
#define FAN_COIL_SETPOINT_C    140.0f
#define FAN_OFF_BELOW_C         50.0f
#define FAN_HYSTERESIS_K         5.0f
#define FAN_DRIVE_CAP            0.8f
#define FAN_COIL_LIMIT_C       150.0f /* R32 tank-current derate start = mean winding limit */
#define FAN_COIL_LIMIT_BAND_K   10.0f /* PROVISIONAL: tank cap 100 % at 150 C to 0 % at 160 C */
#define FAN_KP_PER_K            0.05f /* PROVISIONAL */
#define FAN_KI_PER_K_S          0.002f /* PROVISIONAL */

/* Coil firmware hard trip (C32 ladder): the top of the derate band plus 5 K = 165 C, below the
 * hardware comparator's 169.7 C low corner. Recovery after a coil over-temperature: below the
 * coil fan setpoint, which is under the hardware release band (147.4-157.7 C). */
#define COIL_FW_TRIP_MARGIN_K    5.0f
#define COIL_FW_TRIP_C          (FAN_COIL_LIMIT_C + FAN_COIL_LIMIT_BAND_K + COIL_FW_TRIP_MARGIN_K)
#define COIL_FW_RECOVER_C       FAN_COIL_SETPOINT_C

typedef struct {
    float setpoint_c;
    float integ;
} fan_pi_t;

typedef struct {
    fan_pi_t sink, coil;
    bool on;           /* false: blower switched off (L3: expander P15 FAN_OFF high) */
    float drive;       /* 0 = slowest allowed speed, 1 = full speed */
    bool coil_limit;   /* coil above 150 C: tank derate (coil_tank_cap_pct) */
    uint8_t tank_cap_pct;
} fan_law_t;

/* Tank power cap from the coil temperature: 100 % up to 150 C, linear to 0 % at 160 C, 0 % for an
 * invalid (NaN) reading. The single source of the coil derate: fan_law_step() and coil_guard use
 * it, so the loop and the guard cannot disagree. */
uint8_t coil_tank_cap_pct(float coil_c);

void fan_law_init(fan_law_t *f);
/* fault: any active fault, or an invalid sink/coil reading (NaN) -> on, full speed. */
void fan_law_step(fan_law_t *f, float sink_c, float coil_c, float dt_s, bool fault);

/* ---------------------------------------------------------------- blower tach (L3, C28) */
/* FG pulses per revolution: BLOWER_TACH_PULSES_PER_REV (firmware/config.yaml, misc). The Delta
 * BFB1012VH-F00 sample spec does not state it; set it on the bench. */
#define BLOWER_TACH_WINDOW_MS     250u /* rpm gate time: >= 2 pulses at the stall threshold */

typedef struct {
    bool primed;
    uint16_t last_count;   /* free-running 16-bit pulse count (PCNT) */
    uint32_t window_start_ms;
    uint32_t pulses;       /* pulses in the open window */
    float rpm;             /* last closed window; NaN until the first window closes */
} blower_tach_t;

void blower_tach_init(blower_tach_t *t);
/* count: the PCNT's free-running pulse count (wraps at 16 bits). count_ok=false (read failed)
 * invalidates the reading (NaN), which the stall detector treats as no tach. Returns rpm. */
float blower_tach_update(blower_tach_t *t, bool count_ok, uint16_t count, uint32_t now_ms,
                         unsigned pulses_per_rev);

/* ---------------------------------------------------------------- blower stall (L3, C28) */
#define BLOWER_STALL_RPM         300.0f /* PROVISIONAL: below this while driven = stalled */
#define BLOWER_STALL_TIME_MS      1000u /* R32 / C28: > 1 s */
#define BLOWER_STALL_POWER_CAP_PCT  25u /* PROVISIONAL: "derate tank power at once" */
#define BLOWER_STALL_RISE_K        2.0f /* PROVISIONAL: "stop if the sink or coil keeps rising" */

typedef struct {
    bool below;
    uint32_t below_since_ms;
    bool stalled;
    bool stopped;      /* stalled and still heating: tank stopped until the tach recovers */
    float sink_at_stall, coil_at_stall;
} blower_stall_t;

void blower_stall_init(blower_stall_t *s);
/* Returns the tank power cap, 0..100: 100 normally; BLOWER_STALL_POWER_CAP_PCT once the tach has
 * been below BLOWER_STALL_RPM for > 1 s while driven (a stopped or locked blower, an unplugged one
 * or an open FG wire all read 0); 0 (latched until the tach recovers) if the sink or coil then
 * rises by more than BLOWER_STALL_RISE_K. driven=false (blower off by the fan law) never stalls. */
uint8_t blower_stall_update(blower_stall_t *s, bool driven, float tach_rpm, uint32_t now_ms,
                            float sink_c, float coil_c);

/* ---------------------------------------------------------------- blower speed (L3, C28) */
/* GPIO46 LEDC PWM -> 12.1 k / 1 uF -> 56.2 k into the TPS62933 FB (140 k / 11.5 k). The output
 * FALLS as the duty rises: duty 0 = 11.96-12.40 V (full speed), duty 100 % = 5.03-5.78 V. Duty is
 * capped at BLOWER_PWM_DUTY_MAX so the slowest commanded speed stays >= 6.07 V at every VFB,
 * resistor and v3v3 corner, above the blower's 5.5 V floor (a corner at 5.03 V would stall it and
 * read as a blower failure). Reset / brown-out / MCU off: GPIO46 is an input with the 100 k strap
 * pull-down, so the injection sees 168 k to 0 V and the blower runs at 11.0-11.4 V; firmware duty
 * 0 is the full 12.2 V. Every loss of control therefore means (near) full speed, never stop. */
#define BLOWER_PWM_DUTY_MAX       0.85f

/* drive 0..1 (1 = full speed) -> duty 0..BLOWER_PWM_DUTY_MAX. NaN or out of range fails to full
 * speed (duty 0). */
float blower_pwm_duty_from_drive(float drive);
/* duty -> LEDC compare counts at res_bits (duty 1.0 = 2^res_bits; the controller uses
 * CTRL_BLOWER_LEDC_RES_BITS, controller_board.h); NaN -> 0 (full speed). */
uint32_t blower_ledc_counts(float duty, unsigned res_bits);

/* ---------------------------------------------------------------- blower supply (stage 16, C33) */
/* PS3 (IRM-60-15ST) feeds the blower buck through J13; BLW_PG (expander P16, a 20 k / 4.7 k divider
 * from V15_BLW) reads 1 with PS3 present. The glue hands in the debounced level
 * (controller_board.h ctrl_blw_pg_t: 3 polls at 10 ms; a failed or stale expander read = UNKNOWN). */
typedef enum {
    BLOWER_SUPPLY_UNKNOWN = 0, /* no trustworthy BLW_PG: behave as before C33 (stall path only) */
    BLOWER_SUPPLY_ABSENT,
    BLOWER_SUPPLY_PRESENT,
} blower_supply_t;

/* Diagnosis code, for the UI and the log. It never changes the derate on its own: a stalled blower
 * takes the C28 stall derate (blower_stall_update()) whatever the code says. */
typedef enum {
    BLOWER_DIAG_OK = 0,
    BLOWER_DIAG_STALL,         /* tach < BLOWER_STALL_RPM > 1 s while driven; BLW_PG unknown or
                                * ignored (sense fault): the pre-C33 "stall" fault */
    BLOWER_DIAG_PS3_ABSENT,    /* stalled with BLW_PG = 0; or BLW_PG = 0 with the blower not
                                * turning (idle by the fan law): no cooling available */
    BLOWER_DIAG_BLOWER_FAILED, /* stalled with BLW_PG = 1: supply present, blower or FG failed */
} blower_diag_t;

/* BLW_PG plausibility: BLW_PG = 0 while the tach shows the blower turning (>= BLOWER_STALL_RPM) for
 * longer than this is a BLW_PG sense fault (divider, harness or expander input), latched until MCU
 * reset; BLW_PG is then ignored (UNKNOWN) and the blower falls back to the stall path. It does not
 * derate. PROVISIONAL: long enough to cover a coasting blower after a real PS3 loss (FG normally
 * stops with the fan's supply, but a spinning rotor must not be read as a sense fault). */
#define BLW_PG_PLAUS_TIME_MS 3000u

typedef struct {
    bool contra;            /* BLW_PG = 0 and the tach shows the blower turning */
    uint32_t contra_since_ms;
    bool sense_fault;       /* latched */
} blw_pg_plaus_t;

void blw_pg_plaus_init(blw_pg_plaus_t *p);
/* Returns the supply state to act on: pg, or UNKNOWN once the sense fault has latched. */
blower_supply_t blw_pg_plaus_update(blw_pg_plaus_t *p, blower_supply_t pg, float tach_rpm,
                                    uint32_t now_ms);
/* stalled: blower_stall_t.stalled. supply: after blw_pg_plaus_update(). turning: the tach reads
 * >= BLOWER_STALL_RPM. */
blower_diag_t blower_diagnose(bool stalled, blower_supply_t supply, bool turning);
/* Start interlock: heating may start unless PS3 is reported absent (debounced, plausible). UNKNOWN
 * does not block: the tach / stall path still protects. */
bool blower_start_permitted(blower_supply_t supply);

/* ---------------------------------------------------------------- blower controller */
typedef struct {
    fan_law_t law;
    blower_tach_t tach;
    blower_stall_t stall;
    blw_pg_plaus_t pg;
    blower_supply_t supply; /* last effective BLW_PG (after plausibility) */
    blower_diag_t diag;
} blower_ctrl_t;

typedef struct {
    bool on;            /* false -> expander P15 FAN_OFF high (buck off) */
    float duty;         /* GPIO46 LEDC duty, 0 = full speed */
    float rpm;          /* NaN until the first tach window */
    uint8_t power_cap_pct; /* min(coil derate, stall derate): applied to every tank request */
    bool blower_failed; /* stall detector stopped the tank (is_fan_running() false) */
    /* Stage 16 (C33), filled by blower_ctrl_supply(): */
    blower_diag_t diag;
    bool blw_pg_sense_fault;
    bool start_permitted; /* false: PS3 absent, refuse to start heating */
} blower_cmd_t;

void blower_ctrl_init(blower_ctrl_t *c);
/* One tick: fan law -> on/duty, tach -> rpm, stall -> cap. sink_c / coil_c NaN = invalid (fault
 * path: full speed, coil cap 0). The stall detector runs only while the blower is commanded on. */
blower_cmd_t blower_ctrl_step(blower_ctrl_t *c, float sink_c, float coil_c, bool fault,
                              bool tach_ok, uint16_t tach_count, uint32_t now_ms, float dt_s,
                              unsigned pulses_per_rev);
/* The same tick in two halves, for a gate between the decision and the hardware (stage 16: the
 * PS3 inlet schedule, power/blower_aux.h, holds a speed-up until its inlet allowance is in force):
 * decide() runs the fan law and returns the commanded on/duty; finish() runs the tach and the
 * stall detector against the state actually applied (applied_on), so a held start is not a stall,
 * and fills rpm, power_cap_pct and blower_failed. blower_ctrl_step() = decide + finish(o.on). */
blower_cmd_t blower_ctrl_decide(blower_ctrl_t *c, float sink_c, float coil_c, bool fault, float dt_s);
void blower_ctrl_finish(blower_ctrl_t *c, blower_cmd_t *o, bool applied_on, float sink_c, float coil_c,
                        bool tach_ok, uint16_t tach_count, uint32_t now_ms, unsigned pulses_per_rev);
/* Stage 16 (C33), after finish() in the same tick: BLW_PG plausibility against the tach just
 * read, the diagnosis code and the start interlock. Only labels and the start permit; the tank
 * cap is finish()'s (the C28 derate is the same for "PS3 absent" and "blower failed"). */
void blower_ctrl_supply(blower_ctrl_t *c, blower_cmd_t *o, blower_supply_t blw_pg, uint32_t now_ms);

#endif
