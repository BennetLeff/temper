/**
 * @file mock_tca9555.c
 * @brief TCA9555 (U8) model for the host tests: an I2C transport for the
 *        tca9555 board instance whose Input Port 0 bit 7 (P07, RTD_DRDY) is the
 *        MAX31865 model's DRDY level (mock_max31865.c). Other inputs read high.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "mock_max31865.h"
#include "tca9555.h"

static struct {
    bool fail;
    uint32_t reads;
    uint8_t last_addr;
} t;

static bool write_read(void *ctx, uint8_t addr7, const uint8_t *tx, size_t ntx, uint8_t *rx, size_t nrx)
{
    (void)ctx;
    t.reads++;
    t.last_addr = addr7;
    if (t.fail || tx == NULL || ntx != 1u || rx == NULL || nrx != 1u) {
        return false;   /* NACK / bus error */
    }
    if (tx[0] == TCA9555_REG_INPUT0) {
        rx[0] = mock_max31865_drdy_high() ? 0xFFu : 0x7Fu;
    } else if (tx[0] == TCA9555_REG_INPUT1) {
        rx[0] = 0xFFu;
    } else {
        return false;
    }
    return true;
}

static const tca9555_bus_t s_mock_bus = {.write_read = write_read, .ctx = NULL};

void mock_tca9555_install(void)
{
    t.fail = false;
    t.reads = 0u;
    tca9555_board_set_bus(&s_mock_bus);
}

void mock_tca9555_set_fail(bool fail) { t.fail = fail; }
uint32_t mock_tca9555_reads(void) { return t.reads; }
uint8_t mock_tca9555_last_addr(void) { return t.last_addr; }
