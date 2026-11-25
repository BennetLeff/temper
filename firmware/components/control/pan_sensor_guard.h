/**
 * @file pan_sensor_guard.h
 * @brief Pan-sensor (C1 Pt100) faults and plausibility, sensor-r3 HANDOFF C.4.
 *
 * Checks, per 10 Hz estimator sample:
 *   - MAX31865 fault-status register 07h: RTD high/low threshold, REFIN- high,
 *     REFIN- low (FORCE- open), RTDIN- low (FORCE- open), over/under-voltage,
 *     and a failed SPI status read;
 *   - stale DRDY: no fresh conversion for more than stale_limit samples;
 *   - range: -20 to 320 degC;
 *   - rate: a non-physical reversal (two consecutive steps beyond the 30 K/s
 *     limit with opposite signs, i.e. a spike) or a monotone slew beyond 30 K/s
 *     lasting longer than slew_max_s. A single fast monotone slew is NOT a
 *     fault for C1: placing a hot pan on a cold 40 mJ/K disc legitimately moves
 *     the reading at hundreds of K/s for under a second (firmware/DECISIONS.md
 *     D-RATE, co-sim case hot_pan);
 *   - Pt100-vs-rim-NTC cross-check: while heating, Pt100 < rim - 25 K for 30 s
 *     without rising more than xcheck_max_rise_k makes the sensor suspect,
 *     which asks D1 (contact_check) for a probe.
 *
 * Every fault maps onto the existing state-machine RTD sink
 * state_machine_report_rtd_device_fault(short_fault, open_fault, ctx)
 * (max31865_fault_sink_t), i.e. onto the existing EVENT_PROBE_SHORT /
 * EVENT_PROBE_OPEN transitions: low-resistance classes report a short,
 * everything else reports open/out-of-range, exactly as the MAX31865 driver
 * already classifies register 07h. The diagnostic code keeps the detail.
 */

#ifndef PAN_SENSOR_GUARD_H
#define PAN_SENSOR_GUARD_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* MAX31865 register 07h bits (datasheet Table "Fault Status Register"). */
#define PSG_MAX31865_RTD_HIGH   0x80u
#define PSG_MAX31865_RTD_LOW    0x40u
#define PSG_MAX31865_REFIN_HIGH 0x20u  /* REFIN- > 0.85 x VBIAS          */
#define PSG_MAX31865_REFIN_LOW  0x10u  /* REFIN- < 0.85 x VBIAS, FORCE- open */
#define PSG_MAX31865_RTDIN_LOW  0x08u  /* RTDIN- < 0.85 x VBIAS, FORCE- open */
#define PSG_MAX31865_OVUV       0x04u  /* over/under-voltage              */

typedef enum {
    PSG_OK = 0,
    PSG_FAULT_OPEN = 1,    /**< -> EVENT_PROBE_OPEN / FAULT_PROBE_OPEN   */
    PSG_FAULT_SHORT = 2,   /**< -> EVENT_PROBE_SHORT / FAULT_PROBE_SHORT */
} psg_verdict_t;

typedef enum {
    PSG_DIAG_NONE = 0,
    PSG_DIAG_REG_RTD_HIGH,
    PSG_DIAG_REG_RTD_LOW,
    PSG_DIAG_REG_REFIN_HIGH,
    PSG_DIAG_REG_REFIN_LOW,
    PSG_DIAG_REG_RTDIN_LOW,
    PSG_DIAG_REG_OVUV,
    PSG_DIAG_SPI_READ,
    PSG_DIAG_STALE_DRDY,
    PSG_DIAG_RANGE_HIGH,
    PSG_DIAG_RANGE_LOW,
    PSG_DIAG_NOT_FINITE,
    PSG_DIAG_RATE_SPIKE,
    PSG_DIAG_RATE_SLEW,
} psg_diag_t;

typedef struct {
    float dt_s;               /**< 0.1 */
    float t_min_c;            /**< -20 */
    float t_max_c;            /**< 320 */
    float rate_max_k_per_s;   /**< 30 */
    float slew_max_s;         /**< 3.0: longest physical >30 K/s contact transient */
    uint16_t stale_limit;     /**< samples without a fresh conversion, 3 */
    float xcheck_margin_k;    /**< 25 (sensor-r3 pcb/DECISIONS.md D5: 15 K would
                                   let the rim NTC's 10.2 K error trigger probes
                                   on a correct pan) */
    float xcheck_hold_s;      /**< 30 */
    float xcheck_max_rise_k;  /**< 2.0: the low reading must also not be following
                                   the heating (rise above its lowest value since
                                   the count began < this);
                                   a pan quenched by a cold load rises, a stuck or
                                   low-reading sensor does not (DECISIONS D-XCHK) */
} psg_params_t;

typedef struct {
    float t_pt100_c;
    float t_rim_c;
    bool fresh;               /**< a new conversion arrived this period */
    bool spi_ok;              /**< register 07h read succeeded */
    uint8_t fault_status;     /**< raw register 07h */
    bool heating;             /**< power stage commanded on this period */
} psg_input_t;

typedef struct {
    psg_params_t p;
    bool have_prev;
    float prev_t;
    float prev_step;
    bool have_prev_step;
    uint16_t stale_count;
    uint32_t slew_count;
    int8_t slew_sign;
    uint32_t xcheck_count;
    float xcheck_start_t;     /**< lowest reading since the cross-check count began */
    psg_verdict_t latched;
    psg_diag_t latched_diag;
} psg_t;

typedef struct {
    psg_verdict_t verdict;    /**< latched until psg_init/psg_clear */
    psg_diag_t diag;
    bool sample_valid;        /**< false: do not feed this sample to the estimator */
    bool suspect;             /**< cross-check fired this period: request a D1 probe */
} psg_output_t;

void psg_default_params(psg_params_t *p);
bool psg_init(psg_t *g, const psg_params_t *p);
void psg_clear(psg_t *g);

/** Decode register 07h (and the SPI status) into a verdict and diagnostic. */
psg_verdict_t psg_decode_max31865(uint8_t fault_status, bool spi_ok, psg_diag_t *diag);

void psg_step(psg_t *g, const psg_input_t *in, psg_output_t *out);

/**
 * Deliver a latched verdict to a max31865_fault_sink_t-compatible sink
 * (state_machine_report_rtd_device_fault). Does nothing for PSG_OK.
 */
typedef void (*psg_fault_sink_t)(bool short_fault, bool open_fault, void *context);
void psg_report(psg_verdict_t v, psg_fault_sink_t sink, void *context);

#ifdef __cplusplus
}
#endif

#endif /* PAN_SENSOR_GUARD_H */
