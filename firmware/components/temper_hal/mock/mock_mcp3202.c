/**
 * @file mock_mcp3202.c
 * @brief MCP3202 model on the SPI mock (see mock_max31865.h): single-ended CH1
 *        against the LM4040A25, VDD = VREF = v3v3 (zapote C20).
 */

#include "mock_max31865.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "../include/hal_spi.h"

typedef bool (*mock_spi_transfer_hook_t)(intptr_t device, const hal_spi_transaction_t *t);
extern void mock_spi_set_transfer_hook(mock_spi_transfer_hook_t hook);

static struct {
    bool attached;
    intptr_t dev;
    float v3v3_mv;
    float ref_mv;
    bool absent;
    uint32_t transfers;
} a;

static bool transfer_hook(intptr_t device, const hal_spi_transaction_t *t)
{
    if (!a.attached || device != a.dev || t == NULL) {
        return false;
    }
    a.transfers++;
    if (t->rx_buffer == NULL) {
        return true;
    }
    memset(t->rx_buffer, 0xFF, t->length);
    if (a.absent || t->tx_buffer == NULL || t->length < 3u) {
        return true;   /* DOUT floats high */
    }
    /* DS21034F Figure 6-1: start bit last in byte 0, then SGL/DIFF, ODD/SIGN, MSBF. */
    const uint8_t *tx = t->tx_buffer;
    if (tx[0] != 0x01u || (tx[1] & 0x80u) == 0u) {
        return true;   /* no start / not single-ended: nothing driven */
    }
    const bool ch1 = (tx[1] & 0x40u) != 0u;
    const float vin = ch1 ? a.ref_mv : 0.0f;
    long code = (long)floor(4096.0 * (double)vin / (double)a.v3v3_mv);
    code = code < 0 ? 0 : (code > 4095 ? 4095 : code);
    t->rx_buffer[0] = 0xFFu;
    t->rx_buffer[1] = (uint8_t)(0xE0u | ((code >> 8) & 0x0Fu));   /* high-Z, null 0, B11..B8 */
    t->rx_buffer[2] = (uint8_t)(code & 0xFF);
    return true;
}

void mock_mcp3202_attach(int device_index)
{
    memset(&a, 0, sizeof(a));
    a.attached = true;
    a.dev = (intptr_t)device_index;
    a.v3v3_mv = 3300.0f;
    a.ref_mv = 2500.0f;
    mock_spi_set_transfer_hook(transfer_hook);
}

void mock_mcp3202_detach(void) { a.attached = false; }
void mock_mcp3202_set_v3v3_mv(float mv) { a.v3v3_mv = mv; }
void mock_mcp3202_set_ref_mv(float mv) { a.ref_mv = mv; }
void mock_mcp3202_set_absent(bool absent) { a.absent = absent; }
uint32_t mock_mcp3202_transfers(void) { return a.transfers; }
