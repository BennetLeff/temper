/**
 * @file rail_adc.h
 * @brief v3v3 rail measurement: MCP3202 (U15) CH1 against the LM4040A25 2.5 V
 *        shunt reference, on the RTD SPI bus (zapote/controller C20).
 *
 * The board (zapote/controller controller.ato at controller-c1-crs 467917c38):
 *   u_adc (U15) MCP3202-CI/SN, VDD = VREF = v3v3, CS = GPIO42 (ext_adc_cs_n,
 *   10 k pull-up), CLK/DIN/DOUT on the MAX31865's RTD bus (rtd_sck / rtd_sdi /
 *   rtd_sdo, DOUT through 33 R; high-Z while CS is high); CH0 = tank RMS,
 *   CH1 = ref2v5, the LM4040A25IDBZR (0.1 %) fed from v3v3 through 1 k 1 %.
 * Because the converter's reference is v3v3, CH1's code is
 *   code = 4096 x 2.500 V / v3v3   ->   v3v3 = 2.500 V x 4096 / (code + 0.5)
 * (the +0.5 centres the code; the half-LSB is in the error budget).
 *
 * Bus sharing (DECISIONS.md D-RAIL): rtd_service.c owns the bus and calls
 * rail_adc_board_service() from the control task after its MAX31865 work,
 * at most once per RAIL_ADC_PERIOD_US, so the two devices never contend:
 * one task, sequential transactions, each device with its own ESP-IDF handle,
 * CS, SPI mode and clock (ESP-IDF v5.3.6 spi_master.rst "Driver Features": the
 * driver is thread-safe as long as each device is accessed by one task;
 * spi_features.rst "SPI Bus Lock" time-multiplexes devices on one bus).
 *   MCP3202: SPI modes 0,0 and 1,1 (DS21034F p. 1, section 6.1); fCLK max
 *            0.9 MHz at VDD 2.7 V, 1.8 MHz at 5 V; the sample must be clocked
 *            out within 1.2 ms (>= 10 kHz effective, section 6.2). Mode 0 at
 *            500 kHz: CPOL 0 like the MAX31865's mode 1, so SCLK idles low for
 *            both devices and the MAX31865's CS-edge polarity sampling
 *            ("accommodates either clock polarity", 19-6478 Rev 3) always sees
 *            the same idle level. A reading is 8 x 24 clocks: about 0.4 ms of
 *            bus time per 100 ms; a MAX31865 conversion takes 16.7-17.6 ms,
 *            so DRDY is never missed (the ISR only sets a flag).
 *
 * Validity (no fault; DECISIONS.md D-RAIL): a reading is MEASURED when its
 * value lies in the rail contract (TPS62933, 3.242-3.367 V; pcb/checks.py SRC
 * v3v3) widened by the measurement's own worst-case error at the board's
 * maximum temperature (rail_adc.py -> rail-adc.json, gates the two limits
 * below). Under a single fault the rail is in contract, so a value outside
 * that window means a broken measurement (LM4040 open: code 4095, shorted:
 * code 0; MCP3202 absent: DOUT floats, null bit high), not a broken rail.
 * Then, or after an SPI error, or with no reading for RAIL_ADC_STALE_US, the
 * state is a recorded RAIL_ADC_UNKNOWN_* and the users fall back to the
 * 3.300 V assumption, whose error the as-built budgets already carry (rim
 * 4.37 K, the cold-soak fallback threshold). That is the as-validated state
 * of the board, so it is not a fault.
 */

#ifndef RAIL_ADC_H
#define RAIL_ADC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define RAIL_ADC_REF_MV        2500.0f   /* LM4040A25 */
#define RAIL_ADC_FULL_SCALE    4096.0f
#define RAIL_ADC_SPI_CLOCK_HZ  500000u
#define RAIL_ADC_SPI_MODE      0u
#define RAIL_ADC_SAMPLES       8u        /* conversions averaged per reading */
#define RAIL_ADC_PERIOD_US     100000u   /* one reading per 100 ms */
#define RAIL_ADC_STALE_US      1000000u  /* no accepted reading for 1 s: unknown */
/* Gated by output/temper-sensor-r3/firmware/rail_adc.py (rail-adc.json):
 * 3242 x (1 - e) and 3367 x (1 + e), rounded outward to 5 mV, e the
 * measurement's worst-case error over a -40..85 degC board (1.33 %). */
#define RAIL_ADC_V3V3_MIN_MV   3195.0f
#define RAIL_ADC_V3V3_MAX_MV   3415.0f

/* CS: GPIO42 on zapote/controller (mcu.IO42 ~ ext_adc_cs_n). The board pin map
 * belongs in temper_pins.h (PIN_SPI_CS_EXT_ADC) once it follows the board. */
#ifdef PIN_SPI_CS_EXT_ADC
#define RAIL_ADC_PIN_CS PIN_SPI_CS_EXT_ADC
#else
#define RAIL_ADC_PIN_CS 42
#endif

typedef enum {
    RAIL_ADC_UNKNOWN_NO_READING = 0,  /**< nothing read yet                       */
    RAIL_ADC_MEASURED = 1,            /**< fresh, plausible reading               */
    RAIL_ADC_UNKNOWN_SPI = 2,         /**< transfer failed or the null bit high   */
    RAIL_ADC_UNKNOWN_RANGE = 3,       /**< value outside the widened contract     */
    RAIL_ADC_UNKNOWN_STALE = 4,       /**< last good reading older than STALE_US  */
    RAIL_ADC_UNKNOWN_NO_DEVICE = 5,   /**< the MCP3202 could not be added         */
} rail_adc_state_t;

/** Hardware seam: one full-duplex 3-byte transfer with the MCP3202 selected. */
typedef struct {
    bool (*transfer3)(void *ctx, const uint8_t tx[3], uint8_t rx[3]);
    void *ctx;
} rail_adc_hal_t;

typedef struct {
    rail_adc_state_t state;    /**< state of the latest attempt                 */
    float v3v3_mv;             /**< last accepted value (MEASURED)              */
    float raw_mv;              /**< last computed value, accepted or not        */
    float code_mean;           /**< last mean CH1 code                          */
    uint64_t t_good_us;        /**< time of the last accepted reading           */
    uint64_t t_try_us;         /**< time of the last attempt                    */
    bool have_good;
    bool tried;
    uint32_t attempts;
    uint32_t rejects;
} rail_adc_t;

/** MCP3202 single-ended CH1, MSB first: start bit, SGL/DIFF 1, ODD/SIGN 1, MSBF 1. */
void rail_adc_command(uint8_t tx[3]);

/** 12-bit code from the received bytes; false when the null bit is not low. */
bool rail_adc_decode(const uint8_t rx[3], uint16_t *code);

/** v3v3 in mV from a (mean) CH1 code. */
float rail_adc_code_to_v3v3_mv(float code);

void rail_adc_init(rail_adc_t *r);

/** True when a new reading is due. */
bool rail_adc_due(const rail_adc_t *r, uint64_t now_us);

/** Take one reading (RAIL_ADC_SAMPLES transfers) and update the state. */
rail_adc_state_t rail_adc_sample(rail_adc_t *r, const rail_adc_hal_t *hal, uint64_t now_us);

/** The state at now_us (MEASURED becomes UNKNOWN_STALE after RAIL_ADC_STALE_US). */
rail_adc_state_t rail_adc_state(const rail_adc_t *r, uint64_t now_us);

/** v3v3 in mV when the state is MEASURED at now_us; false otherwise. */
bool rail_adc_v3v3_mv(const rail_adc_t *r, uint64_t now_us, float *mv);

const char *rail_adc_state_name(rail_adc_state_t s);

/* ---- Board instance: U15 on the RTD bus (rtd_service.c owns the bus) ---- */

/** Add the MCP3202 to an initialised SPI bus. A failure leaves the rail unknown. */
hal_status_t rail_adc_board_attach(hal_spi_bus_t bus, const hal_spi_config_t *bus_config);

/** Take a reading if one is due (called by rtd_service_control_tick). */
void rail_adc_board_service(void);

/** The read_v3v3_mv seam of rim_ntc_board.c and hs_ntc_board.c. */
bool rail_adc_board_v3v3_mv(float *mv);

rail_adc_state_t rail_adc_board_state(void);

/** The board instance (diagnostics, tests). */
const rail_adc_t *rail_adc_board(void);

#ifdef __cplusplus
}
#endif

#endif /* RAIL_ADC_H */
