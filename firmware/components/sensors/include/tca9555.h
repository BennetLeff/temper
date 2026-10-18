/**
 * @file tca9555.h
 * @brief Minimal TCA9555 I2C expander input read (U8 on zapote/controller).
 *
 * TI SCPS200E (TCA9555, July 2009, revised April 2019; https://www.ti.com/lit/
 * ds/symlink/tca9555.pdf, retrieved 2026-10-16, sha256 9706a3cc...b231):
 *   Table 3 command bytes: 0x00 Input Port 0, 0x01 Input Port 1, 0x02/0x03
 *   Output, 0x04/0x05 Polarity Inversion (power-up 0000 0000), 0x06/0x07
 *   Configuration (power-up 1111 1111: every pin an input). "Before a read
 *   operation, a write transmission is sent with the command byte" (9.6.1);
 *   the Input Port registers "reflect the incoming logic levels of the pins".
 *   fSCL up to 400 kHz (7.6).
 * A read is therefore a write of the command byte and a repeated-start read of
 * one byte; it changes no expander state (nothing is written but the command
 * pointer, and the INT output, unconnected on this board, is all a read of
 * the input port clears). The pin number is 8 x port + bit (temper_pins.h
 * EXP_* convention). This driver assumes the polarity register is left at its
 * power-up 0, which no firmware writes.
 *
 * Board binding (tca9555_board_*): the I2C bus on PIN_I2C_SDA / PIN_I2C_SCL at
 * TEMPER_EXPANDER_I2C_ADDR (temper_pins.h). The ESP-IDF v5.3.6 I2C master
 * driver is thread-safe only for i2c_new_master_bus() ("Other public I2C APIs
 * are not thread safe", i2c.rst "Thread Safety"), so the binding serialises
 * its transfers with a mutex; host builds take a transport from the test.
 */

#ifndef TCA9555_H
#define TCA9555_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "hal_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define TCA9555_REG_INPUT0 0x00u
#define TCA9555_REG_INPUT1 0x01u
#define TCA9555_I2C_HZ     400000u
#define TCA9555_TIMEOUT_MS 5

/** Transport: write tx (the command byte), repeated start, read rx. */
typedef struct {
    bool (*write_read)(void *ctx, uint8_t addr7, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx);
    void *ctx;
} tca9555_bus_t;

/** Read one input port (0 or 1). */
bool tca9555_read_port(const tca9555_bus_t *bus, uint8_t addr7, unsigned port, uint8_t *value);

/** Read pin (8 x port + bit) level: true = high. */
bool tca9555_read_pin(const tca9555_bus_t *bus, uint8_t addr7, unsigned pin, bool *high);

/* ---- board instance ------------------------------------------------------ */

/** Bring up the board's I2C bus and the expander device (idempotent). */
hal_status_t tca9555_board_attach(void);

/** Host/tests: the transport the board instance uses (NULL detaches). */
void tca9555_board_set_bus(const tca9555_bus_t *bus);

/** Read a board expander pin; false on an I2C error or with no bus. */
bool tca9555_board_read_pin(unsigned pin, bool *high);

/** I2C reads attempted / failed since boot (diagnostics). */
uint32_t tca9555_board_reads(void);
uint32_t tca9555_board_failures(void);

#ifdef __cplusplus
}
#endif

#endif /* TCA9555_H */
