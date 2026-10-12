#ifndef TEMPER_UI_BOARD_MAP_H
#define TEMPER_UI_BOARD_MAP_H
/*
 * Fascia UI board on J7 / SPI3 (zapote/controller DECISIONS C26, branch controller-layout):
 * SSD1322 OLED (CS_OLED# GPIO47, D/C GPIO45) and an MCP23S08 expander (CS_EXP# GPIO48), polled, no
 * interrupt line. The controller side is fixed by C26; the UI board itself is NOT designed yet
 * (DECISIONS open item 3: encoder part, buzzer part, STOP as a hardware trip).
 *
 * PROVISIONAL (firmware decision, 2026-10-12): the MCP23S08 GP bit map below follows the order of
 * the allocation in C26 / controller.ato ("3 buttons, encoder A/B/switch, buzzer, local CS/reset")
 * and the C16 button convention (switch closes to GND, expander pull-up, active low). When the UI
 * board is captured, its schematic replaces this table; nothing else in firmware encodes the map.
 * Until then a board wired differently must not be connected to this firmware.
 */

/* MCP23S08 opcode: 0100 A1 A0 R/W. IOCON.HAEN = 0 (reset default), so the address bits are 00. */
#define UI_EXP_OPCODE_WRITE 0x40u
#define UI_EXP_OPCODE_READ  0x41u

/* MCP23S08 registers (IOCON.BANK does not exist on the 8-bit part). */
#define MCP23S08_IODIR 0x00u /* 1 = input (reset: 0xFF) */
#define MCP23S08_IPOL  0x01u
#define MCP23S08_IOCON 0x05u
#define MCP23S08_GPPU  0x06u /* 1 = 100 k pull-up */
#define MCP23S08_GPIO  0x09u
#define MCP23S08_OLAT  0x0Au

/* GP bit map (PROVISIONAL, see above). Buttons and encoder switch: active low. */
#define UI_BIT_BTN_START  (1u << 0) /* GP0: select/start button (UI board U6) */
#define UI_BIT_BTN_STOP   (1u << 1) /* GP1: stop button */
#define UI_BIT_BTN_BACK   (1u << 2) /* GP2: back button; firmware's BUTTON_BACK, also the fault reset (U6) */
/* GP3-GP5 (encoder A/B/switch) are pending the knob-sensor redesign (UI board revision, owner
 * decision 2026-10-12: tactile switches + magnetic knob on an SPI absolute-angle sensor; one of these
 * bits is probably the sensor CS#). Left as is; do not extend encoder handling. */
#define UI_BIT_ENC_A      (1u << 3)
#define UI_BIT_ENC_B      (1u << 4)
#define UI_BIT_ENC_SW     (1u << 5) /* read, not used by the state machine */
#define UI_BIT_BUZZER     (1u << 6) /* output, high = self-oscillating buzzer on */
#define UI_BIT_TMP_CS     (1u << 7) /* output, TMP122 CS#, idle high = deselected (U6, U10; OLED RES# is an RC) */

/* GP7 is an output driven HIGH (TMP122 deselected). OLAT is written with UI_EXP_OLAT_IDLE before
 * IODIR makes GP7 an output, so the pin never drives low; at power-up/reset it is an input and the
 * board's 10 kohm (R17) holds CS# high. No TMP122 driver exists yet. */
#define UI_EXP_OLAT_IDLE ((uint8_t)UI_BIT_TMP_CS)
#define UI_EXP_IODIR ((uint8_t)(0xFFu & ~(UI_BIT_BUZZER | UI_BIT_TMP_CS)))
#define UI_EXP_GPPU  ((uint8_t)(UI_BIT_BTN_START | UI_BIT_BTN_STOP | UI_BIT_BTN_BACK | UI_BIT_ENC_A | \
                                UI_BIT_ENC_B | UI_BIT_ENC_SW))

/* UI bus timing (zapote/ui-board DECISIONS U13, U14).
 * OLED SSD1322: 8 MHz (cycle >= 100 ns; 62.5 ns half period vs 20 ns min high/low).
 * Expander MCP23S08 (CS_EXP#) and TMP122: at most 5 MHz. At 8 MHz the MISO budget (SO valid 45 ns
 * after SCK fall + ~4 ns RC) leaves 14 ns of the 62.5 ns half period before the ESP32 GPIO-matrix
 * input delay (~25 ns, U13 [UNVERIFIED]) = -11 ns; at 5 MHz (100 ns half period) it is +27 ns.
 * Mode 0 suits all three (SSD1322 samples SDIN on SCLK rising edges; MCP23S08 modes 0,0 / 1,1). */
#define UI_OLED_SPI_CLOCK_HZ 8000000
#define UI_EXP_SPI_CLOCK_HZ  5000000 /* expander and TMP122 (U13); never above this */
#define UI_SPI_MODE       0
/* Frame writes in <= 512-byte chunks, one per UI poll, so input polling is never starved (C26;
 * the SPI3 bus is created with max_transfer_sz = 512 in controller_board_esp32.c). */
#define UI_FRAME_CHUNK    512u
#define UI_POLL_PERIOD_MS 1u    /* C26: the expander is polled at >= 1 kHz */
#define UI_DEBOUNCE_POLLS 15u   /* 15 ms of identical reads: APEM contact bounce is 10 ms (U8, U14.1) */
#define UI_FRAME_MIN_MS   50u   /* at most 20 screen updates per second */
#define UI_PRESENCE_MS    1000u /* re-acquire (re-configure) a lost UI board once a second */
/* UI-lost rule (U14.2, U15): the expander is read (GPIO and IODIR read-back) every poll; with no valid
 * read for MORE than this the UI counts as a STOP (BUTTON_STOP reads pressed). */
#define UI_LOST_STOP_MS   100u
/* OLED: no write within 30 ms of UI power-up (RES# is an on-board RC released 13..18 ms after power,
 * U12); applied before the first oled_init(). */
#define UI_OLED_POWERUP_WAIT_MS 30u

/* SSD1322 window of the NHD-3.12-25664 (256 x 64): column addresses 0x1C..0x5B (4 px each). */
#define SSD1322_COL_START 0x1Cu
#define SSD1322_COL_END   0x5Bu
#define SSD1322_ROW_START 0x00u
#define SSD1322_ROW_END   0x3Fu

#endif
