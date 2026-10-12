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
 *   - Tank ceiling (tank_freq.h): one commissioned value, limits.tank_limit_a (22 A default,
 *     <= 28 A), set with n21_config_set_tank_ceiling(), which derives the RMS trip (1.05 x, on the
 *     half-cycle RMS), the per-sample crest guard (1.5 x) and the peak trip (min(2.17 x + 3, 62)).
 *   - Frequency (COMMISSIONED only): the per-pan loop (tank_freq_step, once per closed half while
 *     the gate is on) sets a target in [f_min, f_max]; the control tick slews the live frequency
 *     towards it by at most step_up_hz per tick, and apply_cycle refuses any other plan or step.
 *     The loop's power target is the adapter's requested_w, handed over by that same tick.
 *     A live change goes through ops.pwm_update (period and compares from shadow registers at
 *     timer zero); with the bridge stopped, through pwm_program. With the gate off the loop is
 *     reset and the frequency returns to f_max.
 *
 * Run gate (COMMISSIONING.md H1): fullbridge_apply qualifies the four PWM captures on every tick,
 * including idle, and expects a separate request/enable to gate the drivers (round-5 REQUEST ->
 * SUP_RUN_OK). Controller layout L2 provides it: RUN_EN (GPIO14) ANDed with the interlock latch by
 * U37 (DECISIONS C23), so the gate can only remove permission. With run_gate == NULL (an earlier
 * capture without U37) the binding refuses N21_MODE_COMMISSIONED; bench bring-up uses the bounded
 * bench session instead.
 */
#include "power_service.h"
#include "line_zc.h"
#include "n21_pins.h"
#include "n21_signal.h"
#include "tank_freq.h"

typedef enum { N21_MODE_INHIBITED = 0, N21_MODE_BENCH = 1, N21_MODE_COMMISSIONED = 2 } n21_mode_t;

typedef struct {
    n21_mode_t mode;           /* zero = INHIBITED: no binding, pads held low */
    bool calibrated;           /* every bench-measured field below has been entered */
    uint32_t timer_hz;         /* MCPWM resolution, 80 MHz */
    tank_freq_cfg_t freq;      /* loop; freq.f_max_hz is the start and the bench-session frequency */
    uint32_t input_deadtime_ns;/* MCU input non-overlap, 200 ns (DECISIONS 2026-10-03 O07) */
    float max_power_w, inlet_target_a, auxiliary_reserve_w;
    input_limits_cfg_t limits; /* input_limits_native21(); est_error from the bench */
    n21_analog_cal_t analog;
    int32_t vsw_delay_ns, ct_zc_delay_ns;
    bool ct_zc_inverted;
    float min_lag_deg;
    line_zc_config_t line_zc;
    float rectifier_drop_v, startup_budget_w;
    /* Derived from limits.tank_limit_a by n21_config_set_tank_ceiling(); may only be lowered. */
    float tank_rms_trip_a;     /* half-cycle RMS trip: 1.05 x ceiling */
    float tank_crest_guard_a;  /* per AD8436 sample: 1.5 x ceiling */
    float tank_peak_trip_a;    /* raw CT_MON instantaneous: min(2.17 x ceiling + 3, 62) A, kept
                                * below TANK_PEAK_TRIP_MAX_A (64.5 A, the stage-15 CT band low
                                * corner 64.55 A); the hardware CT/shunt bands are the backstop */
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
    /* Live retiming while the pads run: same dead time, period and compares loaded from shadow
     * registers at the next timer zero (TEZ) so every period is whole. The binding bounds the step
     * (<= step_up_hz). Required for COMMISSIONED. */
    bool (*pwm_update)(void *, const bridge_cycle_t *);
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
    /* frequency loop */
    uint32_t freq_hz, freq_target_hz, floor_hz;
    float f_res_hz, q, ceiling_eff_a;
    bool pan_present;
    tank_freq_reason_t freq_reason;
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
    tank_freq_t tf;             /* loop state (acquisition context, under lock) */
    uint32_t cycle_hz;          /* frequency of the programmed cycle */
    uint32_t freq_cmd_hz;       /* frequency last handed to the adapter */
    float request_w;            /* adapter requested power, the loop's power target */
    uint64_t last_sample_us, last_report_us, last_reset_us, bench_until_us;
    uint32_t serial, samples;
    uint16_t ref_code;
    float pan_model_w;
    float thermal_limit_a;      /* thermal tank RMS clamp (coil-sensor fault), if thermal_limited */
    bool thermal_limited;
    bool initialized, programmed, pads_live, gate_on, armed_line, invalid, have_sample;
    bool have_reset, bench_active;
} n21_binding_t;

n21_config_t n21_config_default(void);
/* Sets the commissioned tank ceiling (TANK_CEILING_MIN_A..TANK_CEILING_MAX_A) and every trip derived
 * from it. Out of range: false, and the config is made invalid (init refuses it). */
bool n21_config_set_tank_ceiling(n21_config_t *, float ceiling_a);
n21_init_t n21_binding_init(n21_binding_t *, const n21_config_t *, const n21_hw_ops_t *,
                            power_binding_t *out);
void n21_acquire_step(n21_binding_t *);
bool n21_set_pan_model(n21_binding_t *, float watts);
/* Thermal clamp on the tank RMS ceiling (controller L3: a latched coil-sensor fault derates the
 * tank to <= 22 A, thermal_mgmt.h COIL_SENSOR_FAULT_TANK_MAX_A). The frequency loop holds
 * min(commissioned ceiling, clamp); the derived trips stay those of the commissioned ceiling.
 * limited=true needs a finite a >= TANK_CEILING_MIN_A (else false, nothing changes); false clears. */
bool n21_set_thermal_tank_limit(n21_binding_t *, bool limited, float a);
bool n21_request_interlock_reset(n21_binding_t *, bool operator_confirmed);
void n21_telemetry(n21_binding_t *, n21_telemetry_t *);
/* Bench sessions (N21_MODE_BENCH only, adapter not bound): bounded live PWM with every fault
 * check of the acquisition path plus capture timing checked against the programmed cycle. */
bool n21_bench_start(n21_binding_t *, uint32_t duration_ms, bool operator_confirmed);
bool n21_bench_poll(n21_binding_t *);  /* false once stopped (time-out or fault) */
void n21_bench_stop(n21_binding_t *);
#endif
