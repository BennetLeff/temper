/**
 * @file emc2301.c
 * @brief EMC2301 face-fan driver (controller C51). Contract and sources in emc2301.h.
 */
#include "emc2301.h"

#include <stddef.h>

static emc2301_status_t rd(const emc2301_ops_t *ops, uint8_t reg, uint8_t *v)
{
    return ops->read(ops->ctx, reg, v) ? EMC2301_OK : EMC2301_ERR_BUS;
}

/* Write, then read back. */
static emc2301_status_t wr_check(const emc2301_ops_t *ops, uint8_t reg, uint8_t v)
{
    uint8_t back = 0;
    if (!ops->write(ops->ctx, reg, v)) return EMC2301_ERR_BUS;
    if (rd(ops, reg, &back) != EMC2301_OK) return EMC2301_ERR_BUS;
    return back == v ? EMC2301_OK : EMC2301_ERR_READBACK;
}

/* Clear `bits` in `reg` if any is set. */
static emc2301_status_t clear_bits(const emc2301_ops_t *ops, uint8_t reg, uint8_t bits)
{
    uint8_t v = 0;
    emc2301_status_t s = rd(ops, reg, &v);
    if (s != EMC2301_OK || (v & bits) == 0) return s;
    return wr_check(ops, reg, (uint8_t)(v & ~bits));
}

emc2301_status_t emc2301_init(const emc2301_ops_t *ops, uint8_t drive)
{
    if (!ops || !ops->read || !ops->write) return EMC2301_ERR_BUS;
    uint8_t pid = 0, mid = 0, cfg = 0;
    emc2301_status_t s;
    if ((s = rd(ops, EMC2301_REG_PRODUCT_ID, &pid)) != EMC2301_OK) return s;
    if ((s = rd(ops, EMC2301_REG_MFR_ID, &mid)) != EMC2301_OK) return s;
    if (pid != EMC2301_PRODUCT_ID || mid != EMC2301_MFR_ID) return EMC2301_ERR_ID;

    /* 1. Continuous watchdog first (it starts at once, 4.11.2), so the power-up one-shot that the drive
     *    write below disables is never the only protection gone. ALERT# unmasked; DIS_TO as found. */
    if ((s = rd(ops, EMC2301_REG_CONFIG, &cfg)) != EMC2301_OK) return s;
    cfg = (uint8_t)((cfg & ~EMC2301_CONFIG_MASK) | EMC2301_CONFIG_WD_EN);
    if ((s = wr_check(ops, EMC2301_REG_CONFIG, cfg)) != EMC2301_OK) return s;

    /* 2. Open drain (the cascode needs it), normal polarity, direct drive (no RPM loop). */
    if ((s = clear_bits(ops, EMC2301_REG_PWM_OUTPUT, EMC2301_FAN1_BIT)) != EMC2301_OK) return s;
    if ((s = clear_bits(ops, EMC2301_REG_PWM_POL, EMC2301_FAN1_BIT)) != EMC2301_OK) return s;
    if ((s = clear_bits(ops, EMC2301_REG_FAN_CONFIG1, EMC2301_FANCFG1_ENAG)) != EMC2301_OK) return s;

    /* 3. The drive. */
    return wr_check(ops, EMC2301_REG_FAN_SETTING, drive);
}

emc2301_status_t emc2301_service(const emc2301_ops_t *ops, uint8_t drive, emc2301_poll_t *out)
{
    emc2301_poll_t p = {0};
    uint8_t cfg = 0, status = 0, setting = 0, hi = 0, lo = 0;
    emc2301_status_t s;
    if (!ops || !ops->read || !ops->write) return EMC2301_ERR_BUS;

    /* A reset part (v3v3 dip) has WD_EN clear and drive 0: set it up again. */
    if ((s = rd(ops, EMC2301_REG_CONFIG, &cfg)) != EMC2301_OK) return s;
    if (!(cfg & EMC2301_CONFIG_WD_EN) && (s = emc2301_init(ops, drive)) != EMC2301_OK) return s;

    if ((s = rd(ops, EMC2301_REG_FAN_STATUS, &status)) != EMC2301_OK) return s;
    p.watchdog_expired = (status & EMC2301_STATUS_WATCH) != 0;
    p.drive_fail = (status & EMC2301_STATUS_DVFAIL) != 0;
    p.spin_fail = (status & EMC2301_STATUS_FNSPIN) != 0;
    p.stall_untrusted = (status & EMC2301_STATUS_FNSTL) != 0;

    /* After an expiry the part holds 100 % until Fan Setting is written, whatever the register reads. */
    if ((s = rd(ops, EMC2301_REG_FAN_SETTING, &setting)) != EMC2301_OK) return s;
    if (p.watchdog_expired || setting != drive) {
        if ((s = wr_check(ops, EMC2301_REG_FAN_SETTING, drive)) != EMC2301_OK) return s;
        setting = drive;
    }
    p.drive = setting;

    /* High byte first: it latches the low byte (6.1). 13-bit count in [12:5] and [4:0]. */
    if ((s = rd(ops, EMC2301_REG_TACH_HIGH, &hi)) != EMC2301_OK) return s;
    if ((s = rd(ops, EMC2301_REG_TACH_LOW, &lo)) != EMC2301_OK) return s;
    p.tach_count = (uint16_t)(((uint16_t)hi << 5) | (lo >> 3));

    if (out) *out = p;
    return EMC2301_OK;
}
