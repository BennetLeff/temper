#ifndef TEMPER_N21_BINDING_H
#define TEMPER_N21_BINDING_H
/*
 * Native-21 power-stage binding for the integrated SELV controller (zapote/controller).
 *
 * It implements power_binding_t (power_service.h) over a small HAL table (n21_hw_ops_t), so all of
 * the logic here is host-testable with fakes; firmware/components/power/n21_hw_esp32.c is the
 * ESP32-S3 implementation of the table. Two execution contexts share one n21_binding_t:
 *   - n21_acquire_step(): the acquisition context, every acq_period_us (625 us = 13 samples per
 *     half line cycle). Reads VBUS/CT_MON (ADC1), the AD8436 tank RMS (MCP3202), CT_ZC phase and
 *     LINE_ZC edges; assembles each half line cycle and runs input_limits_half_cycle on it.
 *   - power_service_tick() -> sample()/backend: the control task (10 ms), the adapter's sole owner.
 * ops.lock/unlock guard the shared state.
 *
 * Safety properties (each has a host test):
 *   - commissioned=false by default: n21_config_default() is N21_MODE_INHIBITED and nothing binds.
 *   - Firmware never asserts PERMIT. The HAL table has no PERMIT output; the only interlock output
 *     is the IL_RESET_N request, issued solely by n21_request_interlock_reset() with an explicit
 *     operator confirmation, never from a fault, sample or tick path, and never while PWM is live.
 *   - Any input fault (BUS_FAULT, RAIL_OK, PERMIT, SUP_RUN_OK, VBUS invalid/over-range, CT_MON,
 *     RMS channel, CT_ZC phase, tank RMS over the envelope, LINE_ZC loss) or a stale sample makes
 *     sample() return false, which power_service turns into a latched inhibit.
 *
 * Hardware gap (see COMMISSIONING.md "Open hardware questions", H1): fullbridge_apply qualifies the
 * four PWM captures on every tick, including idle, and expects a separate request/enable to gate
 * the drivers (round-5 REQUEST -> SUP_RUN_OK). The integrated controller has no firmware-driven
 * driver enable: PERMIT comes only from the interlock latch, so while PERMIT is high, live PWM pads
 * ARE a running bridge. With run_gate == NULL (the controller as captured) the binding therefore
 * refuses N21_MODE_COMMISSIONED. Bench bring-up uses the bounded bench session instead.
 */
#include "power_service.h"
#include "line_zc.h"
#include "n21_pins.h"
#include "n21_signal.h"

typedef enum { N21_MODE_INHIBITED = 0, N21_MODE_BENCH = 1, N21_MODE_COMMISSIONED = 2 } n21_mode_t;

typedef struct {
    n21_mode_t mode;           /* zero = INHIBITED: no binding, pads held low */
    bool calibrated;           /* every bench-measured field below has been entered */
    uint32_t timer_hz;         /* MCPWM resolution, 80 MHz */
    uint32_t frequency_hz;     /* fixed bridge frequency; 0 = not set (bench item) */
    uint32_t input_deadtime_ns;/* MCU input non-overlap, 200 ns (DECISIONS 2026-10-03 O07) */
    float max_power_w, inlet_target_a, auxiliary_reserve_w;
    input_limits_cfg_t limits; /* input_limits_native21(); est_error from the bench */
    n21_analog_cal_t analog;
    int32_t vsw_delay_ns, ct_zc_delay_ns;
    bool ct_zc_inverted;
    float min_lag_deg;
    line_zc_config_t line_zc;
    float rectifier_drop_v, startup_budget_w;
    float tank_rms_trip_a;     /* envelope enforcement: 22 A x 1.05 */
    float tank_peak_trip_a;    /* raw CT_MON instantaneous, below the 50.9 A hardware band */
    float cos_phi_min_current_a; /* below this CT_ZC is undefined: cos(phi) := 1 (conservative) */
    uint32_t acq_period_us, sample_max_age_us, ct_zc_max_age_us, capture_age_us, half_max_gap_us;
    uint32_t bench_max_ms;
} n21_config_t;

typedef struct {
    uint64_t (*now_us)(void *);
    void (*lock)(void *);
    void (*unlock)(void *);
    /* PWM. program: only while the pads are not live. outputs(false) must leave all four pads
     * low (force + GPIO low, D-25) and is attempted even after a failure. */
    bool (*pwm_program)(void *, const bridge_cycle_t *);
    bool (*pwm_outputs)(void *, bool live);
    bool (*pwm_capture)(void *, n21_pwm_capture_t *);
    /* Firmware driver enable ANDed into PERMIT. NULL on the controller as captured (gap H1). */
    bool (*run_gate)(void *, bool on);
    bool (*read_status)(void *, n21_status_rb_t *);
    /* IL_RESET_N falling edge. The latch grants PERMIT only with every source healthy. */
    bool (*interlock_reset_pulse)(void *);
    bool (*read_adc1)(void *, float *vbus_mv, float *ct_mon_mv);
    bool (*read_ext_adc)(void *, unsigned channel, uint16_t *code); /* MCP3202 under bus lock */
    bool (*read_ct_zc)(void *, uint32_t *zc_ticks, uint64_t *t_us);
    size_t (*line_zc_edges)(void *, uint64_t *t_us, bool *level, size_t max);
    void *ctx;
} n21_hw_ops_t;

typedef enum {
    N21_FAULT_NONE = 0, N21_FAULT_HW, N21_FAULT_VBUS_OVERRANGE, N21_FAULT_CT_MON,
    N21_FAULT_TANK_PEAK, N21_FAULT_RMS_CHANNEL, N21_FAULT_TANK_RMS, N21_FAULT_PHASE,
    N21_FAULT_CT_ZC_STALE, N21_FAULT_PWM
} n21_fault_t;

typedef enum {
    N21_INIT_ERROR = 0,      /* bad config/HAL: pads low, nothing bound */
    N21_INIT_INHIBITED,      /* default: pads low, acquisition for telemetry only */
    N21_INIT_BENCH,          /* bench sessions allowed, adapter not bound */
    N21_INIT_BIND,           /* *out is ready for power_service_bind (commissioned) */
    N21_INIT_NO_RUN_GATE,    /* COMMISSIONED refused: hardware gap H1 */
    N21_INIT_NOT_CALIBRATED  /* COMMISSIONED refused: calibration record incomplete */
} n21_init_t;

typedef struct {
    float bus_v, ct_mon_a, tank_rms_a, cos_phi, phi_rad, v3v3;
    n21_half_result_t last_half;
    uint32_t halves_ok, halves_bad;
    bool have_half, zc_locked, pads_live, gate_on, armed_line, bench_active, sample_invalid;
    n21_fault_t fault;
} n21_telemetry_t;

typedef struct {
    n21_config_t cfg;
    n21_hw_ops_t ops;
    n21_mode_t mode;
    bridge_cycle_t cycle;
    n21_phase_cfg_t phase;
    line_zc_t zc;
    n21_half_t half;
    n21_line_agg_t agg;
    n21_telemetry_t tm;
    n21_fault_t fault;          /* latched until reset */
    uint64_t last_sample_us, last_report_us, last_reset_us, bench_until_us;
    uint32_t serial, samples;
    uint16_t ref_code;
    float pan_model_w;
    bool initialized, programmed, pads_live, gate_on, armed_line, invalid, have_sample;
    bool have_reset, bench_active;
} n21_binding_t;

n21_config_t n21_config_default(void);
n21_init_t n21_binding_init(n21_binding_t *, const n21_config_t *, const n21_hw_ops_t *,
                            power_binding_t *out);
void n21_acquire_step(n21_binding_t *);
bool n21_set_pan_model(n21_binding_t *, float watts);
bool n21_request_interlock_reset(n21_binding_t *, bool operator_confirmed);
void n21_telemetry(n21_binding_t *, n21_telemetry_t *);
/* Bench sessions (N21_MODE_BENCH only, adapter not bound): bounded live PWM with every fault
 * check of the acquisition path plus capture timing checked against the programmed cycle. */
bool n21_bench_start(n21_binding_t *, uint32_t duration_ms, bool operator_confirmed);
bool n21_bench_poll(n21_binding_t *);  /* false once stopped (time-out or fault) */
void n21_bench_stop(n21_binding_t *);
#endif
