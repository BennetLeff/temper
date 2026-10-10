#ifndef TEMPER_THERMAL_MGMT_H
#define TEMPER_THERMAL_MGMT_H
/*
 * Thermal management for the integrated controller (pure C, host-tested by
 * firmware/test/test_thermal_mgmt.c):
 *
 *  - NTC divider conversion for the controller's NTC channels. The R36 rim NTC (GPIO9, ADC1_CH8,
 *    DECISIONS C27) is built like the coil channel: 10.0 k 0.1 % pull-up to v3v3, NTC to selv_gnd,
 *    10 k / 100 nF, unity CMOS follower, 100 R / 100 nF into the pad.
 *  - Pan temperature cap, 250 C (owner 2026-10-09, R32 CONTROLLER-SPEC): a power cap from the pan
 *    RTD and, independently and more slowly, from the rim NTC (R36 DECISIONS 4: "an independent,
 *    slower path to the 250 C cap; glass temperature").
 *  - Fan law (R32): drive = max(sink loop, coil loop); PI on the heatsink NTC at 88.6 C and on the
 *    coil NTC at 140 C; off below 50 C with 5 K hysteresis; drive cap 0.8 except in a fault (then
 *    full speed); coil above 150 C (the mean winding limit) derates tank power, at any fan drive.
 *  - Blower stall detection (C28): tach below threshold for > 1 s while driven derates tank power
 *    at once, and stops it if the sink or coil keeps rising.
 *
 * Values marked PROVISIONAL have no measured basis yet and must be set on the bench.
 */
#include <stdbool.h>
#include <stdint.h>

/* ---------------------------------------------------------------- NTC channels */
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

typedef struct {
    float r_pullup_ohm;         /* to v_ref */
    float r25_ohm;              /* NTC at 25 C */
    float beta_k;               /* B25/85, used when curve == NULL */
    const ntc_curve_t *curve;   /* manufacturer R-T model; NULL = beta model */
    float v_ref_mv;             /* divider supply (v3v3, C8: 3.304 V nominal) */
    float t_open_c;             /* a node implying colder than this = open NTC / unplugged */
    float t_short_c;            /* a node implying hotter than this = shorted NTC */
} ntc_channel_t;

/* Rim (R36 "glass-encapsulated 10 k NTC, rated >= 300 C"): the pull-up and the NTC are being
 * changed in hardware (rim resolution at 250 C); the values below drop in from these macros, and
 * every threshold follows from them. B 3950 K is PROVISIONAL (R36 names no part). */
#ifndef RIM_NTC_R_PULLUP_OHM
#define RIM_NTC_R_PULLUP_OHM 10000.0f
#endif
#ifndef RIM_NTC_R25_OHM
#define RIM_NTC_R25_OHM      10000.0f
#endif
#ifndef RIM_NTC_BETA_K
#define RIM_NTC_BETA_K        3950.0f
#endif
extern const ntc_channel_t THERMAL_NTC_RIM;
/* Coil and heatsink: Vishay NTCALUG01A104GA on a 10.0 k pull-up (thermal-sense block). */
extern const ntc_channel_t THERMAL_NTC_COIL;
extern const ntc_channel_t THERMAL_NTC_SINK;

typedef enum { NTC_OK = 0, NTC_OPEN, NTC_SHORT, NTC_BAD_ARG } ntc_status_t;

/* NTC resistance at a temperature, and the inverse, through the channel's model. */
float ntc_channel_r_at(const ntc_channel_t *ch, float temp_c);
ntc_status_t ntc_channel_temp_c(const ntc_channel_t *ch, float mv, float *temp_c);
/* Inverse (divider voltage at a temperature): for thresholds and tests. */
float ntc_channel_mv_at(const ntc_channel_t *ch, float temp_c);

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

typedef struct {
    float setpoint_c;
    float integ;
} fan_pi_t;

typedef struct {
    fan_pi_t sink, coil;
    bool on;           /* false: blower switched off (L3: expander P15 FAN_OFF high) */
    float drive;       /* 0 = slowest (5.5 V floor), 1 = full speed */
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

/* ---------------------------------------------------------------- blower stall (L3, C28) */
#define BLOWER_STALL_TACH_HZ      10.0f /* PROVISIONAL: FG below this while driven = stalled */
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
 * been low for > 1 s while driven; 0 (latched until the tach recovers) if the sink or coil then
 * rises by more than BLOWER_STALL_RISE_K. driven=false (blower off by the fan law) never stalls. */
uint8_t blower_stall_update(blower_stall_t *s, bool driven, float tach_hz, uint32_t now_ms,
                            float sink_c, float coil_c);

/* STUB (controller L3, hardware in progress): drive -> GPIO46 LEDC duty into the buck FB. The
 * converter's output falls as the duty rises (duty 0 = ~12 V full speed, the fail-safe), so the
 * duty is 1 - drive here. The real map is closed on the tach by the speed loop once J10 exists. */
float blower_pwm_duty_from_drive(float drive);

#endif
