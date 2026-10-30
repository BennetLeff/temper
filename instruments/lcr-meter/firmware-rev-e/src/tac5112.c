#include <stddef.h>
#include "tac5112.h"

typedef struct {
    uint8_t reg, value;
} reg_value;

/* Written after the wake-up wait, in this order. Channel enables and power come last
   (SLASF24A 7.4.2). Defaults kept: ADC channel 1 on slot 0 and channel 2 on slot 1, DAC
   channel 1 from slot 0, 2.75 V VREF, 0 dB digital volume, VCOM 1.65 V. Word length and
   filters depend on the sample-rate build (tac5112.h). */
static const reg_value config[] = {
    {TAC_INTF_CFG1, TAC_DOUT_ASI},
    {TAC_PASI_CFG0, TAC_PASI_FORMAT}, /* TDM, 32- or 24-bit, standard polarities, bus-error recovery on */
    {TAC_PASI_TX_CH1_CFG, 0x20u}, /* ADC channel 1 -> slot 0 */
    {TAC_PASI_TX_CH2_CFG, 0x21u}, /* ADC channel 2 -> slot 1 */
    {TAC_PASI_RX_CH1_CFG, 0x20u}, /* slot 0 -> DAC channel 1 */
    {TAC_PASI_RX_CH2_CFG, 0x01u}, /* DAC channel 2 input disabled */
    {TAC_ADC_CH1_CFG0, TAC_ADC_CFG},
    {TAC_ADC_CH2_CFG0, TAC_ADC_CFG},
    {TAC_OUT1X_CFG1, 0x21u},      /* line out, 0 dB, DAC_CH1_BW_MODE wideband */
    /* Filters for the build's rate (tac5112.h), HPF = programmable IIR at its all-pass
       default, no biquads, no soft-stepping: nothing in the path depends on the data. */
    {TAC_DSP_CFG0, TAC_DSP_FILTERS},
    {TAC_DSP_CFG1, TAC_DSP_FILTERS},
    {TAC_CH_EN, TAC_CHANNELS},
};

static tac5112_status put(const tac5112_io *io, uint8_t reg, uint8_t value) {
    return io->write(io->context, reg, value) ? TAC_OK : TAC_ERR_BUS;
}

tac5112_status tac5112_check(const tac5112_io *io, uint8_t power_expected) {
    uint8_t power = 0, mode = 0, rate = 0;
    if (!io->read(io->context, TAC_DEV_STS0, &power) || !io->read(io->context, TAC_DEV_STS1, &mode) ||
        !io->read(io->context, TAC_CLK_DET_STS0, &rate))
        return TAC_ERR_BUS;
    uint8_t want = power_expected == TAC_POWER_ALL ? TAC_CHANNELS : (TAC_CHANNELS & 0xF0u);
    if ((power & want) != want) return TAC_ERR_POWER;
    if ((mode >> 5) != 7u) return TAC_ERR_MODE;
    if ((rate >> 2) != TAC_RATE_BIN) return TAC_ERR_CLOCK;
    return TAC_OK;
}

tac5112_status tac5112_power(const tac5112_io *io, uint8_t power) {
    tac5112_status status = put(io, TAC_PWR_CFG, power);
    if (status != TAC_OK) return status;
    io->sleep_ms(io->context, 50u);
    return tac5112_check(io, power);
}

tac5112_status tac5112_clock_flags(const tac5112_io *io, uint8_t *err0, uint8_t *err1) {
    if (!io->read(io->context, TAC_CLK_ERR_STS0, err0) || !io->read(io->context, TAC_CLK_ERR_STS1, err1))
        return TAC_ERR_BUS;
    *err0 &= TAC_CLK_ERR0_MASK;
    *err1 &= TAC_CLK_ERR1_MASK;
    return TAC_OK;
}

uint32_t tac5112_settle_remaining_ms(uint32_t since_ms) {
    return since_ms >= TAC_ADC_SETTLE_MS ? 0u : TAC_ADC_SETTLE_MS - since_ms;
}

/* Power down, write CLK_CFG0, power up again and read the flags: one clock setting tried. A
   wrong detected rate (TAC_ERR_CLOCK) is a result; any other failure is returned as is. */
static tac5112_status clock_try(const tac5112_io *io, uint8_t clk_cfg0, tac5112_clock *clock) {
    tac5112_status status = put(io, TAC_PWR_CFG, 0u);
    if (status != TAC_OK) return status;
    io->sleep_ms(io->context, 50u);
    if ((status = put(io, TAC_CLK_CFG0, clk_cfg0)) != TAC_OK) return status;
    status = tac5112_power(io, TAC_POWER_ALL);
    if (status != TAC_OK && status != TAC_ERR_CLOCK) return status;
    tac5112_status flags = tac5112_clock_flags(io, &clock->err0, &clock->err1);
    return flags != TAC_OK ? flags : status;
}

tac5112_status tac5112_start_report(const tac5112_io *io, tac5112_clock *clock) {
    tac5112_clock local;
    if (!clock) clock = &local;
    clock->mode = TAC_CLOCK_AUTO;
    clock->err0 = clock->err1 = 0;
    tac5112_status status = put(io, TAC_PAGE_CFG, 0u);
    if (status == TAC_OK) status = put(io, TAC_SW_RESET, 1u);
    if (status != TAC_OK) return status;
    /* 10 ms before the exit-sleep write (7.4.1 asks this after entering sleep; a reset
       ends in sleep, so the same wait is applied). */
    io->sleep_ms(io->context, 10u);
    if ((status = put(io, TAC_PAGE_CFG, 0u)) != TAC_OK) return status;
    if ((status = put(io, TAC_DEV_MISC_CFG, TAC_WAKE)) != TAC_OK) return status;
    /* Channel registers only 10 ms after leaving sleep (7.4.2); VREF settles within its 10 ms
       quick charge (TAC_WAKE). */
    io->sleep_ms(io->context, TAC_WAKE_MS);
    uint8_t misc = 0;
    if (!io->read(io->context, TAC_MISC_CFG1, &misc)) return TAC_ERR_BUS;
    misc = (uint8_t)((misc & ~TAC_INCAP_QCHG_MASK) | TAC_INCAP_QCHG_12_5MS);
    if ((status = put(io, TAC_MISC_CFG1, misc)) != TAC_OK) return status;
    for (unsigned i = 0; i < sizeof config / sizeof config[0]; ++i)
        if ((status = put(io, config[i].reg, config[i].value)) != TAC_OK) return status;
    status = tac5112_power(io, TAC_POWER_ALL);
    if (status != TAC_OK && status != TAC_ERR_CLOCK) return status;
    tac5112_status flags = tac5112_clock_flags(io, &clock->err0, &clock->err1);
    if (flags != TAC_OK) return flags;
    /* Clock fallback (audit C-05), only on a wrong detected rate or a CLK_ERR_STS flag: first
       PASI_FS_RATE_NO_LIM (5 % auto tolerance), then the fixed bin (semi-automatic). CLK_CFG0
       is a pre-power-up setting, so the channels go down around each write. */
    static const struct {
        uint8_t clk_cfg0;
        tac5112_clock_mode mode;
    } fallback[] = {{TAC_CLK_NO_LIM, TAC_CLOCK_NO_LIM}, {TAC_CLK_FIXED, TAC_CLOCK_FIXED}};
    for (unsigned i = 0; i < sizeof fallback / sizeof fallback[0] && (status != TAC_OK || clock->err0 || clock->err1); ++i) {
        clock->mode = fallback[i].mode;
        if ((status = clock_try(io, fallback[i].clk_cfg0, clock)) != TAC_OK && status != TAC_ERR_CLOCK) return status;
    }
    if (status != TAC_OK || clock->err0 || clock->err1) {
        /* Neither setting helped: back to the reset value, so a flag that has nothing to do
           with the rate (and a rate the codec still detects) leaves the validated default. */
        clock->mode = TAC_CLOCK_ERROR;
        tac5112_clock settings;
        status = clock_try(io, TAC_CLK_AUTO, &settings);
        if (status != TAC_OK && status != TAC_ERR_CLOCK) return status;
    }
    return status;
}

tac5112_status tac5112_start(const tac5112_io *io) { return tac5112_start_report(io, NULL); }

const char *tac5112_clock_name(tac5112_clock_mode mode) {
    switch (mode) {
    case TAC_CLOCK_AUTO: return "auto";
    case TAC_CLOCK_NO_LIM: return "no_lim";
    case TAC_CLOCK_FIXED: return "fixed";
    case TAC_CLOCK_ERROR: return "error";
    }
    return "unknown";
}

const char *tac5112_status_name(tac5112_status status) {
    switch (status) {
    case TAC_OK: return "ok";
    case TAC_ERR_BUS: return "codec_bus";
    case TAC_ERR_POWER: return "codec_power";
    case TAC_ERR_MODE: return "codec_mode";
    case TAC_ERR_CLOCK: return "codec_clock";
    }
    return "codec";
}
