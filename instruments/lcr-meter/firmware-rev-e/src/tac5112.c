#include "tac5112.h"

typedef struct {
    uint8_t reg, value;
} reg_value;

/* Written after the wake-up wait, in this order. Channel enables and power come last
   (SLASF24A 7.4.2). Defaults kept: TDM, 32-bit slots, ADC channel 1 on slot 0 and channel 2
   on slot 1, DAC channel 1 from slot 0, 2.75 V VREF, 0 dB digital volume, VCOM 1.65 V. */
static const reg_value config[] = {
    {TAC_INTF_CFG1, TAC_DOUT_ASI},
    {TAC_PASI_CFG0, 0x30u},       /* TDM, 32-bit, standard polarities, bus-error recovery on */
    {TAC_PASI_TX_CH1_CFG, 0x20u}, /* ADC channel 1 -> slot 0 */
    {TAC_PASI_TX_CH2_CFG, 0x21u}, /* ADC channel 2 -> slot 1 */
    {TAC_PASI_RX_CH1_CFG, 0x20u}, /* slot 0 -> DAC channel 1 */
    {TAC_PASI_RX_CH2_CFG, 0x01u}, /* DAC channel 2 input disabled */
    {TAC_ADC_CH1_CFG0, TAC_ADC_CFG},
    {TAC_ADC_CH2_CFG0, TAC_ADC_CFG},
    {TAC_OUT1X_CFG1, 0x21u},      /* line out, 0 dB, DAC_CH1_BW_MODE wideband */
    /* Linear-phase filters, HPF = programmable IIR at its all-pass default, no biquads,
       no soft-stepping: nothing in the path depends on the data. */
    {TAC_DSP_CFG0, 0x02u},
    {TAC_DSP_CFG1, 0x02u},
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

tac5112_status tac5112_start(const tac5112_io *io) {
    tac5112_status status = put(io, TAC_PAGE_CFG, 0u);
    if (status == TAC_OK) status = put(io, TAC_SW_RESET, 1u);
    if (status != TAC_OK) return status;
    /* 10 ms before the exit-sleep write (7.4.1 asks this after entering sleep; a reset
       ends in sleep, so the same wait is applied). */
    io->sleep_ms(io->context, 10u);
    if ((status = put(io, TAC_PAGE_CFG, 0u)) != TAC_OK) return status;
    if ((status = put(io, TAC_DEV_MISC_CFG, TAC_WAKE)) != TAC_OK) return status;
    /* Channel registers only 10 ms after leaving sleep (7.4.2); VREF settles in 3.5 ms. */
    io->sleep_ms(io->context, 10u);
    for (unsigned i = 0; i < sizeof config / sizeof config[0]; ++i)
        if ((status = put(io, config[i].reg, config[i].value)) != TAC_OK) return status;
    return tac5112_power(io, TAC_POWER_ALL);
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
