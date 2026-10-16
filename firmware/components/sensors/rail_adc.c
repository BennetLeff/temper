/**
 * @file rail_adc.c
 * @brief v3v3 from MCP3202 CH1 against the LM4040A25 (see rail_adc.h;
 *        output/temper-sensor-r3/firmware/DECISIONS.md D-RAIL).
 */

#include "rail_adc.h"

#include <math.h>
#include <string.h>

#include "hal.h"

void rail_adc_command(uint8_t tx[3])
{
    /* DS21034F Figure 6-1 (mode 0,0): seven leading zeros and the start bit,
     * then SGL/DIFF = 1, ODD/SIGN = 1 (CH1), MSBF = 1, then don't-care clocks
     * while B11..B0 come back. */
    tx[0] = 0x01u;
    tx[1] = 0xE0u;
    tx[2] = 0x00u;
}

bool rail_adc_decode(const uint8_t rx[3], uint16_t *code)
{
    /* Second byte: three high-Z bits, the null bit (low), B11..B8; third: B7..B0.
     * A missing or unpowered converter leaves DOUT floating: a high null bit is
     * an SPI error, not a code. */
    if (code == NULL || (rx[1] & 0x10u) != 0u) {
        return false;
    }
    *code = (uint16_t)(((uint16_t)(rx[1] & 0x0Fu) << 8) | rx[2]);
    return true;
}

float rail_adc_code_to_v3v3_mv(float code)
{
    if (!(code >= 0.0f)) {
        return NAN;
    }
    return RAIL_ADC_REF_MV * RAIL_ADC_FULL_SCALE / (code + 0.5f);
}

void rail_adc_init(rail_adc_t *r)
{
    if (r == NULL) {
        return;
    }
    memset(r, 0, sizeof(*r));
    r->state = RAIL_ADC_UNKNOWN_NO_READING;
    r->v3v3_mv = NAN;
    r->raw_mv = NAN;
    r->code_mean = NAN;
}

bool rail_adc_due(const rail_adc_t *r, uint64_t now_us)
{
    return r != NULL && (!r->tried || now_us < r->t_try_us || now_us - r->t_try_us >= RAIL_ADC_PERIOD_US);
}

rail_adc_state_t rail_adc_sample(rail_adc_t *r, const rail_adc_hal_t *hal, uint64_t now_us)
{
    if (r == NULL) {
        return RAIL_ADC_UNKNOWN_NO_READING;
    }
    r->tried = true;
    r->t_try_us = now_us;
    r->attempts++;
    if (hal == NULL || hal->transfer3 == NULL) {
        r->state = RAIL_ADC_UNKNOWN_NO_DEVICE;
        r->rejects++;
        return r->state;
    }
    uint32_t sum = 0u;
    for (unsigned i = 0u; i < RAIL_ADC_SAMPLES; i++) {
        uint8_t tx[3];
        uint8_t rx[3] = {0xFFu, 0xFFu, 0xFFu};
        uint16_t code = 0u;
        rail_adc_command(tx);
        if (!hal->transfer3(hal->ctx, tx, rx) || !rail_adc_decode(rx, &code)) {
            r->state = RAIL_ADC_UNKNOWN_SPI;
            r->rejects++;
            return r->state;
        }
        sum += code;
    }
    r->code_mean = (float)sum / (float)RAIL_ADC_SAMPLES;
    r->raw_mv = rail_adc_code_to_v3v3_mv(r->code_mean);
    if (!isfinite(r->raw_mv) || r->raw_mv < RAIL_ADC_V3V3_MIN_MV || r->raw_mv > RAIL_ADC_V3V3_MAX_MV) {
        r->state = RAIL_ADC_UNKNOWN_RANGE;
        r->rejects++;
        return r->state;
    }
    r->v3v3_mv = r->raw_mv;
    r->t_good_us = now_us;
    r->have_good = true;
    r->state = RAIL_ADC_MEASURED;
    return r->state;
}

rail_adc_state_t rail_adc_state(const rail_adc_t *r, uint64_t now_us)
{
    if (r == NULL) {
        return RAIL_ADC_UNKNOWN_NO_READING;
    }
    if (r->state == RAIL_ADC_MEASURED &&
        (now_us < r->t_good_us || now_us - r->t_good_us > RAIL_ADC_STALE_US)) {
        return RAIL_ADC_UNKNOWN_STALE;
    }
    return r->state;
}

bool rail_adc_v3v3_mv(const rail_adc_t *r, uint64_t now_us, float *mv)
{
    if (mv == NULL || rail_adc_state(r, now_us) != RAIL_ADC_MEASURED) {
        return false;
    }
    *mv = r->v3v3_mv;
    return true;
}

const char *rail_adc_state_name(rail_adc_state_t s)
{
    switch (s) {
    case RAIL_ADC_UNKNOWN_NO_READING: return "unknown: no reading";
    case RAIL_ADC_MEASURED: return "measured";
    case RAIL_ADC_UNKNOWN_SPI: return "unknown: SPI";
    case RAIL_ADC_UNKNOWN_RANGE: return "unknown: out of range";
    case RAIL_ADC_UNKNOWN_STALE: return "unknown: stale";
    case RAIL_ADC_UNKNOWN_NO_DEVICE: return "unknown: no device";
    default: return "?";
    }
}

/* ---- Board instance ------------------------------------------------------- */

static rail_adc_t s_board;
static bool s_board_inited;
static bool s_board_attached;
static hal_spi_device_t s_board_dev;

static void board_init_once(void)
{
    if (!s_board_inited) {
        rail_adc_init(&s_board);
        s_board_inited = true;
    }
}

static uint64_t board_now_us(void)
{
    return (uint64_t)HAL_TIME_US();
}

static bool board_transfer3(void *ctx, const uint8_t tx[3], uint8_t rx[3])
{
    (void)ctx;
    if (hal_spi == NULL || hal_spi->transfer == NULL || !s_board_attached) {
        return false;
    }
    const hal_spi_transaction_t t = {.tx_buffer = tx, .rx_buffer = rx, .length = 3u};
    return hal_spi->transfer(s_board_dev, &t) == HAL_OK;
}

static const rail_adc_hal_t s_board_hal = {.transfer3 = board_transfer3, .ctx = NULL};

hal_status_t rail_adc_board_attach(hal_spi_bus_t bus, const hal_spi_config_t *bus_config)
{
    rail_adc_init(&s_board);
    s_board_inited = true;
    s_board_attached = false;
    if (hal_spi == NULL || bus_config == NULL) {
        s_board.state = RAIL_ADC_UNKNOWN_NO_DEVICE;
        return HAL_ERROR_NOT_READY;
    }
    hal_spi_config_t cfg = *bus_config;
    cfg.clock_hz = RAIL_ADC_SPI_CLOCK_HZ;
    cfg.mode = RAIL_ADC_SPI_MODE;
    cfg.pin_cs = RAIL_ADC_PIN_CS;
    cfg.cs_active_high = false;
    const hal_status_t st = hal_spi->device_add(bus, &cfg, &s_board_dev);
    if (st != HAL_OK) {
        s_board.state = RAIL_ADC_UNKNOWN_NO_DEVICE;
        return st;
    }
    s_board_attached = true;
    return HAL_OK;
}

void rail_adc_board_service(void)
{
    board_init_once();
    if (!s_board_attached) {
        return;
    }
    const uint64_t now = board_now_us();
    if (rail_adc_due(&s_board, now)) {
        (void)rail_adc_sample(&s_board, &s_board_hal, now);
    }
}

bool rail_adc_board_v3v3_mv(float *mv)
{
    board_init_once();
    return rail_adc_v3v3_mv(&s_board, board_now_us(), mv);
}

rail_adc_state_t rail_adc_board_state(void)
{
    board_init_once();
    return s_board_attached || s_board.state != RAIL_ADC_UNKNOWN_NO_READING
               ? rail_adc_state(&s_board, board_now_us())
               : RAIL_ADC_UNKNOWN_NO_READING;
}

const rail_adc_t *rail_adc_board(void)
{
    board_init_once();
    return &s_board;
}
