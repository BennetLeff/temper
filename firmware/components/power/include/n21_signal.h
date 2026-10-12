#ifndef TEMPER_N21_SIGNAL_H
#define TEMPER_N21_SIGNAL_H
/*
 * Native-21 binding, pure signal layer: unit conversion, MCP3202 framing, the cos(phi) estimate,
 * the per-half-line-cycle sample assembly and the PWM-capture -> bridge_feedback_t mapping.
 * No HAL, no globals: everything here is host-tested (firmware/test/test_n21_binding.c).
 *
 * Every scale factor cites zapote/controller/tools/controller_calcs.py (committed evidence in
 * zapote/controller/evidence/controller_calcs.json); none is invented here.
 */
#include "fullbridge_adapter.h"
#include "input_limits.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* ---- VBUS: controller_calcs.d11_receiver -------------------------------------------------
 * V_adc = bias + 0.5 * k * V_bus, bias = 2.5 * 10 / (90.9 + 10) = 0.24777 V (LM4040A25 over the
 * fitted 90.9k/10.0k, DECISIONS C10), k = 15.8k / (4 x 470k + 15.8k) (D-11 divider), 0.5 = the
 * OPA2388 half-gain difference stage. 0/170/198 V -> 0.2478/0.9562/1.0729 V. ATTEN2 (0-1600 mV).
 * D-11 / D-20 O13: < 100 mV invalid (receiver or J4 lost), >= 1210 mV over-range latch (231 V). */
#define N21_VBUS_BIAS_V      0.2477700693756194f
#define N21_VBUS_K           (15.8e3f / (4.0f * 470e3f + 15.8e3f))
#define N21_VBUS_V_PER_V     (0.5f * N21_VBUS_K)
#define N21_VBUS_INVALID_MV  100.0f
#define N21_VBUS_OVERRANGE_MV 1210.0f
/* ---- CT_MON raw: controller_calcs.ct_mon --------------------------------------------------
 * 1.65 V + I_tank x 15 mV/A (1:100 CT into 1.5 ohm); TLV9062 follower, 10 MOhm to 0 V so an
 * unplugged J4 reads ~0 V. ATTEN3 0-2900 mV; 55 A peak trip spans 0.825-2.475 V. */
#define N21_CT_MON_BIAS_V    1.65f
#define N21_CT_MON_V_PER_A   0.015f
#define N21_CT_MON_MIN_MV    50.0f    /* below: unplugged / buffer dead */
#define N21_CT_MON_MAX_MV    2850.0f  /* ATTEN3 2900 mV less its +/-50 mV accuracy */
/* ---- Tank RMS: controller_calcs.rms_channel ------------------------------------------------
 * AD8436 RMS of ct_mon (15 mV/A) x gain 4 (30k/10k) = 60 mV/A: 22 A -> 1.32 V. MCP3202 VREF is
 * v3v3; CH1 reads the LM4040A25 2.500 V so V_ch0 = 2.5 * code0 / code1 (ratiometric). The v3v3
 * contract 3.135-3.465 V bounds code1 to [2955.3, 3266.3]; anything else is a broken reference. */
#define N21_RMS_V_PER_A      0.060f
#define N21_LM4040_V         2.5f
#define N21_V3V3_MIN_V       3.135f
#define N21_V3V3_MAX_V       3.465f

typedef enum { N21_SIG_OK = 0, N21_SIG_INVALID, N21_SIG_OVERRANGE } n21_sig_t;

/* Factory/bench trims; zero-initialised = nominal scaling (gain trim 0 means 1.0). */
typedef struct {
    float vbus_offset_mv;   /* measured reading at 0 V bus minus nominal bias, mV */
    float vbus_gain_trim;   /* multiplicative, 0 => 1.0; bench: DMM bus vs reading */
    float ct_mon_zero_mv;   /* measured idle CT_MON level, 0 => 1650 mV nominal */
    float rms_gain_trim;    /* multiplicative, 0 => 1.0; bench: current probe vs reading */
} n21_analog_cal_t;

n21_sig_t n21_vbus_from_mv(const n21_analog_cal_t *, float adc_mv, float *bus_v);
n21_sig_t n21_ct_mon_from_mv(const n21_analog_cal_t *, float adc_mv, float *tank_a);
n21_sig_t n21_tank_rms_from_codes(const n21_analog_cal_t *, uint16_t code_rms, uint16_t code_ref,
                                  float *tank_rms_a, float *v3v3);
/* Line RMS from the unsmoothed bus peak (DECISIONS 2026-10-08 input-current entry: "V_line from the
 * bus peak"). rectifier_drop_v = 0 under-reads the line, which over-reads I_ps: conservative. */
float n21_line_rms_from_bus_peak(float bus_peak_v, float rectifier_drop_v);

/* MCP3202 single-ended read (DS21034F fig. 6-1, 8-bit segments; SPI mode 0 or 3): start bit,
 * then SGL=1, ODD/SIGN=channel, MSBF=1. 12-bit result in rx[1] low nibble and rx[2]. */
void n21_mcp3202_frame(unsigned channel, uint8_t tx[3]);
bool n21_mcp3202_decode(const uint8_t rx[3], uint16_t *code);

/* ---- cos(phi) from CT_ZC against the PWM timing -----------------------------------------------
 * The bridge voltage V_A - V_B steps positive when leg A's raw generator rises at the PWM timer
 * zero (LA and HB commands fall at tick 0, HA/LB rise one dead time later; bridge_plan_cycle).
 * Its fundamental crosses zero (rising) at that switch-node transition, i.e. timer zero plus
 * vsw_delay (driver propagation + part of the ZVS transition; bench-calibrated). The tank current's
 * rising zero is the CT_ZC rising edge less ct_zc_delay (CT + TLV3201 delay; bench). Its lag behind
 * the voltage is phi; inductive operation has phi > 0. CT_ZC polarity is a bench item: invert adds
 * half a period. phi below min_lag_rad (capacitive or too close to it, D-20 O06) is refused. */
typedef struct {
    uint32_t period_ticks;   /* programmed bridge period, timer ticks */
    int32_t vsw_delay_ticks;
    int32_t ct_zc_delay_ticks;
    bool ct_zc_inverted;
    float min_lag_rad;
} n21_phase_cfg_t;
/* zc_ticks: CT_ZC rising edge, ticks after PWM timer zero (capture timer phase-locked to TEZ). */
bool n21_cos_phi(const n21_phase_cfg_t *, uint32_t zc_ticks, float *cos_phi, float *phi_rad);

/* ---- Half-line-cycle assembly ------------------------------------------------------------------
 * Samples between two consecutive LINE_ZC predicted zeros. Close() requires the D-11 half-cycle
 * spacing (7833-8834 us), >= 8 samples, no gap longer than max_gap_us (including from the opening
 * zero and to the closing one), then calls input_limits_half_cycle with V_line from the bus peak. */
#define N21_HALF_MAX_SAMPLES 48
typedef struct {
    input_sample_t s[N21_HALF_MAX_SAMPLES];
    uint64_t start_us, last_us;
    uint64_t max_gap_us;
    size_t n;
    float bus_peak_v;
    /* Frequency loop inputs (n21_half_note): bridge frequency, CT_ZC lag, raw CT_MON peak. */
    uint32_t f_lo_hz, f_hi_hz, f_last_hz, phi_n;
    float phi_sum, ct_abs_max_a;
    bool open, broken;
} n21_half_t;
typedef struct {
    uint64_t end_us;
    float line_rms_v;
    input_estimate_t est;
    uint32_t f_hz;          /* bridge frequency at the last sample */
    uint32_t f_lo_hz, f_hi_hz; /* frequency range over the half */
    uint32_t phi_n;         /* samples with a CT_ZC lag */
    float phi_mean_rad;     /* NAN when phi_n == 0 */
    float ct_abs_max_a;     /* largest |CT_MON| sample */
    float rms_sample_max_a; /* largest AD8436 sample (the envelope crest) */
} n21_half_result_t;
void n21_half_begin(n21_half_t *, uint64_t zero_us);
/* Out-of-order, overflow or not-open marks the half broken (it will not close). */
void n21_half_add(n21_half_t *, uint64_t t_us, const input_sample_t *);
/* Per-sample loop inputs: the live bridge frequency, the lag when CT_ZC measured one, |CT_MON|. */
void n21_half_note(n21_half_t *, uint32_t f_hz, bool phi_valid, float phi_rad, float ct_abs_a);
bool n21_half_close(n21_half_t *, const input_limits_cfg_t *, uint64_t zero_us,
                    uint32_t max_gap_us, float rectifier_drop_v, n21_half_result_t *);
/* As n21_half_close with the auxiliary allowance in force for this half (input_limits_aux()). */
bool n21_half_close_aux(n21_half_t *, const input_limits_cfg_t *, float aux_a, uint64_t zero_us,
                        uint32_t max_gap_us, float rectifier_drop_v, n21_half_result_t *);

/* ---- Line-cycle report -----------------------------------------------------------------------
 * fullbridge_line_cycle wants one complete line record every 14-22 ms. The binding reports every
 * second 10 ms control tick, folding every half cycle completed since the previous report into the
 * worst case: max inlet bound, min tank ceiling, min line voltage (lower V = lower budget). */
typedef struct {
    uint64_t last_end_us;
    float line_rms_v, inlet_bound_a, tank_ceiling_w, tank_rms_a;
    uint32_t halves;
} n21_line_agg_t;
void n21_line_agg_add(n21_line_agg_t *, const n21_half_result_t *);
/* pan_budget = min(pan model, tank ceiling); with no tank-current evidence (ceiling = INFINITY)
 * the startup budget stands in, so the adapter never sees a non-finite budget. */
bool n21_line_report(const n21_line_agg_t *, float pan_model_w, float startup_budget_w,
                     float *line_v, float *inlet_a, float *pan_budget_w);

/* ---- PWM capture -> bridge_feedback_t ----------------------------------------------------------
 * Per output (A_H, A_L, B_H, B_L): first rising edge after a PWM timer zero (ticks), its high
 * time and the rise-to-rise period, from MCPWM capture of the pad (GPIO loop-back). Non-overlap is
 * this output's rise minus its complement's fall (A_H<->A_L, B_H<->B_L), modulo the period. */
typedef struct { uint32_t rise, high, period; bool valid; } n21_edge_t;
typedef struct { uint64_t t_us; n21_edge_t out[4]; } n21_pwm_capture_t;
typedef struct { bool permit, bus_fault, rail_ok, sup_run_ok; } n21_status_rb_t;
void n21_feedback_from_capture(const n21_pwm_capture_t *, const n21_status_rb_t *,
                               uint32_t serial, bridge_feedback_t *);
/* The adapter's own acceptance window (fullbridge_apply), for the bench PWM session, which runs
 * without the adapter. Kept equal to fullbridge_apply by test. */
bool n21_capture_matches(const bridge_cycle_t *, const bridge_feedback_t *);
#endif
