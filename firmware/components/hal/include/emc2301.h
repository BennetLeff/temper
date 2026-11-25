/**
 * @file emc2301.h
 * @brief EMC2301 face-fan controller (controller C51, U52 at 0x2F on the internal I2C bus).
 *
 * Source: Microchip DS20006532A (EMC2301/2/3/5, 2021), Table 6-1, Registers 6-1 / 6-2, section 4.11.
 * Board: zapote/controller/elec/src/bay_fan_block.ato (branch controller-c51); DECISIONS C51 "Face fan".
 *
 * What the board relies on:
 *  - At power-up the drive is 0 and the one-shot watchdog sets 100 % after 4 s unless the Fan Setting
 *    register is written (4.11.1). Writing Fan Setting disables that power-up watchdog.
 *  - With WD_EN set (Configuration bit 5) the watchdog runs continuously: any SMBus access restarts its
 *    4 s, and on expiry every fan goes to 100 % until it is programmed again (4.11.2, Register 6-2 WATCH).
 *    So an MCU that stops servicing the part gives full speed within 4 s. emc2301_init() sets WD_EN
 *    BEFORE the first Fan Setting write, so no instant exists with neither watchdog armed.
 *  - While the watchdog is active the part does not check for a stalled fan (4.11), so a stall flag is
 *    reported but never trusted (C51: "must not count on stall detection").
 *  - PWM is open drain into a cascode BSS138 (gate on v3v3); the fan's own pull-up makes "released" =
 *    drive. Normal polarity and open drain are the POR values (2Ah, 2Bh = 00h); init checks both.
 */
#ifndef EMC2301_H
#define EMC2301_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define EMC2301_I2C_ADDR        0x2Fu /* 0101_111, CLK pin strap (C51) */

#define EMC2301_REG_CONFIG      0x20u
#define EMC2301_REG_FAN_STATUS  0x24u /* read-then-clear */
#define EMC2301_REG_PWM_POL     0x2Au
#define EMC2301_REG_PWM_OUTPUT  0x2Bu
#define EMC2301_REG_FAN_SETTING 0x30u
#define EMC2301_REG_FAN_CONFIG1 0x32u
#define EMC2301_REG_TACH_HIGH   0x3Eu /* read high first: it latches the low byte (6.1) */
#define EMC2301_REG_TACH_LOW    0x3Fu
#define EMC2301_REG_PRODUCT_ID  0xFDu
#define EMC2301_REG_MFR_ID      0xFEu

#define EMC2301_CONFIG_MASK     0x80u
#define EMC2301_CONFIG_DIS_TO   0x40u
#define EMC2301_CONFIG_WD_EN    0x20u
#define EMC2301_FAN1_BIT        0x01u /* PLRTY1 / PM1OT */
#define EMC2301_FANCFG1_ENAG    0x80u /* RPM loop; this driver uses direct drive */

#define EMC2301_STATUS_WATCH    0x80u
#define EMC2301_STATUS_DVFAIL   0x04u
#define EMC2301_STATUS_FNSPIN   0x02u
#define EMC2301_STATUS_FNSTL    0x01u

#define EMC2301_PRODUCT_ID      0x37u
#define EMC2301_MFR_ID          0x5Du

#define EMC2301_DRIVE_FULL      0xFFu

/* Service at least this often; the continuous watchdog expires after 4 s (4.11.2). */
#define EMC2301_SERVICE_PERIOD_MS 1000u

typedef struct {
    bool (*read)(void *ctx, uint8_t reg, uint8_t *value);
    bool (*write)(void *ctx, uint8_t reg, uint8_t value);
    void *ctx;
} emc2301_ops_t;

typedef enum {
    EMC2301_OK = 0,
    EMC2301_ERR_BUS,       /* a transfer failed: the part's own watchdog takes the fan to 100 % */
    EMC2301_ERR_ID,        /* product or manufacturer ID is not an EMC2301 */
    EMC2301_ERR_READBACK,  /* a register did not hold what was written */
} emc2301_status_t;

typedef struct {
    bool watchdog_expired; /* WATCH was set: the fan ran at 100 % and has just been re-programmed */
    bool drive_fail;
    bool spin_fail;
    bool stall_untrusted;  /* FNSTL as read; not checked by the part while its watchdog runs */
    uint8_t drive;         /* Fan Setting as read back */
    uint16_t tach_count;   /* 13-bit TACH reading; no RPM conversion until a fan is selected */
} emc2301_poll_t;

/* Identify the part, arm the continuous watchdog, check open-drain normal-polarity direct drive, then
 * write the drive. On any error the caller keeps calling emc2301_service(), which retries init. */
emc2301_status_t emc2301_init(const emc2301_ops_t *ops, uint8_t drive);

/* One service: read the status (clears it and restarts the watchdog), re-program the drive if the
 * watchdog expired or the setting differs from `drive`, read the tachometer. */
emc2301_status_t emc2301_service(const emc2301_ops_t *ops, uint8_t drive, emc2301_poll_t *out);

#ifdef __cplusplus
}
#endif

#endif
