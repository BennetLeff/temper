#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/bootrom.h"
#include "pico/stdio_usb.h"
#include "pico/unique_id.h"
#include "hardware/adc.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/i2c.h"
#include "hardware/pio.h"
#include "tusb.h"
#include "pins.h"
#include "relay.h"
#include "syncavg.h"
#include "tac5112.h"
#include "wave.h"
#if LCR_FS_375K
#include "tdm375.pio.h"
#define TDM_PROGRAM tdm375_program
#define TDM_DEFAULT_CONFIG tdm375_program_get_default_config
#else
#include "tdm.pio.h"
#define TDM_PROGRAM tdm_program
#define TDM_DEFAULT_CONFIG tdm_program_get_default_config
#endif

/* RX DMA ring: two words per frame, 8192 words = 4096 frames (21.8 ms at 187.5 kHz, 10.9 ms
   at 375 kHz). Size and alignment are equal so the DMA write-address ring wrap works. */
#define RING_WORDS 8192u
#define RING_SIZE_BITS 15u
static uint32_t ring[RING_WORDS] __attribute__((aligned(RING_WORDS * 4u)));
/* Capture output: int64 bin sums (CAPTURE) or int32 frames (RAW) share one buffer. */
#define RAW_MAX_FRAMES 8192u
static union {
    int64_t sum[2u * WAVE_MAX_PERIOD];
    int32_t raw[2u * RAW_MAX_FRAMES];
} out;
static int32_t header[4];
/* Two waveform buffers: the DMA plays one while the other is written. */
static int32_t wave_buffer[2][WAVE_MAX_PERIOD];
static uint wave_active = 0;
static uint32_t wave_period = WAVE_MIN_PERIOD;
static uint32_t wave_cycles = 0, wave_mv = 0; /* 0, 0: silent or uploaded */
/* Read by the TX control DMA channel: the start of the waveform to replay. */
static const int32_t *volatile tx_source;
/* Written by the snapshot DMA channel at every waveform wrap: the RX channel's live
   TRANS_COUNT. Zero means no snapshot since the firmware cleared it. */
static volatile uint32_t snap_count;

static PIO tdm_pio = pio0;
static uint tdm_sm;
static int ch_txd, ch_txc, ch_snap, ch_rxd;
static bool codec_ok = false;
static int range_ohm = 0;
static char unit_id[PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2 + 1];

/* ---------------------------------------------------------------- codec over I2C */
static bool i2c_put(void *context, uint8_t reg, uint8_t value) {
    (void)context;
    uint8_t buffer[2] = {reg, value};
    return i2c_write_timeout_us(i2c0, CODEC_I2C_ADDRESS, buffer, 2, false, 5000) == 2;
}
static bool i2c_get(void *context, uint8_t reg, uint8_t *value) {
    (void)context;
    return i2c_write_timeout_us(i2c0, CODEC_I2C_ADDRESS, &reg, 1, true, 5000) == 1 &&
           i2c_read_timeout_us(i2c0, CODEC_I2C_ADDRESS, value, 1, false, 5000) == 1;
}
static void io_sleep(void *context, uint32_t ms) {
    (void)context;
    sleep_ms(ms);
}
static const tac5112_io codec = {0, i2c_put, i2c_get, io_sleep};

/* ---------------------------------------------------------------- TDM stream */
/* The stream never stops: BCLK and FSYNC run from boot so the codec PLL stays locked.
   TXD plays tx_source[0..TRANS_COUNT) into the PIO TX FIFO and chains to TXC, which
   re-triggers TXD from tx_source and chains to SNAP, which copies RXD's TRANS_COUNT to
   snap_count. The chain fires right after the PIO's mid-slot-1 pull, so every snapshot
   falls between the frame's two pushes: the word after it is always slot 1. */
static void rx_arm(void) {
    dma_channel_abort(ch_rxd);
    dma_channel_config c = dma_channel_get_default_config(ch_rxd);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, true);
    channel_config_set_ring(&c, true, RING_SIZE_BITS);
    channel_config_set_dreq(&c, pio_get_dreq(tdm_pio, tdm_sm, false));
    dma_channel_configure(ch_rxd, &c, ring, &tdm_pio->rxf[tdm_sm], UINT32_MAX, true);
}
static uint32_t rx_issued(const void *context) {
    (void)context;
    return UINT32_MAX - dma_channel_hw_addr(ch_rxd)->transfer_count;
}
/* Wait for the next waveform wrap and return the RX words written before it; false on
   timeout (TX chain not running). The value is read once: the next wrap overwrites it. */
static bool wait_snapshot(uint32_t *issued) {
    snap_count = 0;
    absolute_time_t deadline = make_timeout_time_ms(50);
    uint32_t count;
    while ((count = snap_count) == 0)
        if (time_reached(deadline)) return false;
    if (issued) *issued = UINT32_MAX - count;
    return true;
}
static void stream_start(void) {
    memset(wave_buffer, 0, sizeof wave_buffer);
    tx_source = wave_buffer[0];
    const uint tdm_pins[] = {PIN_I2S_DIN, PIN_I2S_DOUT, PIN_I2S_BCLK, PIN_I2S_FSYNC};
    for (unsigned i = 0; i < 4; ++i) pio_gpio_init(tdm_pio, tdm_pins[i]);
    uint offset = pio_add_program(tdm_pio, &TDM_PROGRAM);
    pio_sm_config config = TDM_DEFAULT_CONFIG(offset);
    sm_config_set_out_pins(&config, PIN_I2S_DIN, 1);
    sm_config_set_in_pins(&config, PIN_I2S_DOUT);
    sm_config_set_sideset_pins(&config, PIN_I2S_BCLK);
    sm_config_set_out_shift(&config, false, false, 32);
    sm_config_set_in_shift(&config, false, false, 32);
    sm_config_set_clkdiv_int_frac(&config, 1, 0);
    pio_sm_init(tdm_pio, tdm_sm, offset, &config);
    pio_sm_set_consecutive_pindirs(tdm_pio, tdm_sm, PIN_I2S_DOUT, 1, false);
    pio_sm_set_consecutive_pindirs(tdm_pio, tdm_sm, PIN_I2S_DIN, 1, true);
    pio_sm_set_consecutive_pindirs(tdm_pio, tdm_sm, PIN_I2S_BCLK, 2, true);
    /* DOUT is synchronous to our own BCLK and stable for the whole bit around the sampling
       edge, so the input synchronizer only costs margin: without it the falling-edge sample
       sees the pad half a BCLK (41.7 ns at 187.5 kHz, 27.8 ns at 375 kHz) after the codec's
       launch edge (td <= 14 ns + pad and rise). */
    tdm_pio->input_sync_bypass |= 1u << PIN_I2S_DOUT;

    dma_channel_config c = dma_channel_get_default_config(ch_snap);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, false);
    dma_channel_configure(ch_snap, &c, &snap_count, &dma_hw->ch[ch_rxd].transfer_count, 1, false);

    c = dma_channel_get_default_config(ch_txc);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, false);
    channel_config_set_chain_to(&c, ch_snap);
    dma_channel_configure(ch_txc, &c, &dma_hw->ch[ch_txd].al3_read_addr_trig, &tx_source, 1, false);

    c = dma_channel_get_default_config(ch_txd);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, pio_get_dreq(tdm_pio, tdm_sm, true));
    channel_config_set_chain_to(&c, ch_txc);
    dma_channel_configure(ch_txd, &c, &tdm_pio->txf[tdm_sm], tx_source, wave_period, true);

    rx_arm();
    pio_sm_set_enabled(tdm_pio, tdm_sm, true);
}
/* Make wave_buffer[next] (already written) the waveform from the next wrap on. The swap
   happens right after a wrap, at least 16 frames (43 us at 375 kHz) before the next one, with
   interrupts off so the two writes stay together; the call returns once the new waveform
   has started. Both buffers only ever hold words within the source limit (a rejected
   upload is zeroed), so even a swap split by a wrap could only play one period of
   in-limit words. */
static bool wave_activate(uint next, uint32_t period) {
    /* RXD's count runs out after 2^32 words (3.2 h); its TRANS_COUNT is the snapshot, so
       re-arm it before relying on one. Captures re-arm it themselves. */
    rx_arm();
    if (!wait_snapshot(NULL)) return false;
    uint32_t interrupts = save_and_disable_interrupts();
    dma_channel_hw_addr(ch_txd)->transfer_count = period; /* reload value, used at next trigger */
    tx_source = wave_buffer[next];
    restore_interrupts(interrupts);
    wave_active = next;
    wave_period = period;
    if (wait_snapshot(NULL)) return true;
    wave_cycles = wave_mv = 0; /* swapped in but not confirmed: do not claim a tone */
    return false;
}
static bool wave_silence(void) {
    uint next = wave_active ^ 1u;
    memset(wave_buffer[next], 0, sizeof wave_buffer[next]);
    wave_cycles = wave_mv = 0;
    return wave_activate(next, WAVE_MIN_PERIOD);
}

/* ---------------------------------------------------------------- capture */
typedef enum { CAPTURE_OK, CAPTURE_SYNC, CAPTURE_OVERRUN, CAPTURE_STREAM, CAPTURE_CODEC } capture_result;
static const char *capture_error(capture_result r) {
    switch (r) {
    case CAPTURE_SYNC: return "stream_sync";
    case CAPTURE_OVERRUN: return "acquisition_overrun";
    case CAPTURE_STREAM: return "stream_fault";
    case CAPTURE_CODEC: return "codec_status";
    default: return "ok";
    }
}
/* Capture `frames` frames starting `skip` frames after a waveform wrap, into averaging
   bins (sum != NULL, one bin per waveform index) or raw frames. Capture frame j meets
   DAC word (j + skip - 5) mod period at the PIO pins: the 4-word TX FIFO plus the OSR
   hold five words ahead of the refill that fires the snapshot. */
static capture_result capture(syncavg_t *s, uint32_t skip, uint8_t power, uint32_t timeout_ms) {
    rx_arm();
    const uint32_t stall = (1u << (PIO_FDEBUG_TXSTALL_LSB + tdm_sm)) | (1u << (PIO_FDEBUG_RXSTALL_LSB + tdm_sm));
    uint32_t issued;
    if (!wait_snapshot(&issued)) return CAPTURE_SYNC;
    tdm_pio->fdebug = stall; /* write 1 to clear: drops while the ring was re-armed are expected */
    /* The snapshot falls between the frame's two pushes: skip its slot 1. */
    const uint32_t start = issued + 1u + 2u * skip;
    absolute_time_t deadline = make_timeout_time_ms(timeout_ms);
    capture_result result = CAPTURE_OK;
    while (result == CAPTURE_OK && s->done < s->frames) {
        if (!syncavg_drain(s, ring, RING_WORDS, start, rx_issued, NULL)) result = CAPTURE_OVERRUN;
        else if (time_reached(deadline)) result = CAPTURE_SYNC;
    }
    if (result == CAPTURE_OK && (tdm_pio->fdebug & stall)) result = CAPTURE_STREAM;
    if (result == CAPTURE_OK && tac5112_check(&codec, power) != TAC_OK) result = CAPTURE_CODEC;
    syncavg_extremes(s, header);
    return result;
}

/* ---------------------------------------------------------------- self-test */
/* Digital loopback: DOUT echoes DIN (INTF_CFG1 DOUT_SEL 14) with the DAC powered down.
   A pseudo-random period-61 pattern within the source limit is played; two raw captures
   must each return slot 0 = pattern[(j - 5) mod 61] >> 8 and slot 1 = 0 for every frame.
   This checks the PIO bit timing, word order, DMA chain and the snapshot alignment. */
#define LOOP_PERIOD 61u
#define LOOP_FRAMES (4u * LOOP_PERIOD)
static const char *selftest(void) {
    /* A codec that lost its configuration (brown-out, bus fault) is brought up again once. */
    if (tac5112_check(&codec, TAC_POWER_ALL) != TAC_OK && tac5112_start(&codec) != TAC_OK)
        return "codec_status";
    if (!wave_silence()) return "stream_sync";
    const char *failure = NULL;
    if (tac5112_power(&codec, TAC_POWER_ADC) != TAC_OK) failure = "codec_power";
    else if (!i2c_put(0, TAC_INTF_CFG1, TAC_DOUT_LOOPBACK)) failure = "codec_bus";
    uint next = wave_active ^ 1u;
    uint32_t x = 0x2545f491u;
    for (uint32_t k = 0; k < LOOP_PERIOD; ++k) {
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        wave_buffer[next][k] = (int32_t)((int64_t)(x % (2u * (uint32_t)SOURCE_LIMIT_CODE + 1u)) - SOURCE_LIMIT_CODE);
    }
    if (!failure && !wave_activate(next, LOOP_PERIOD)) failure = "stream_sync";
    for (int pass = 0; pass < 2 && !failure; ++pass) {
        syncavg_t s;
        syncavg_init_raw(&s, out.raw, LOOP_FRAMES);
        capture_result r = capture(&s, 0, TAC_POWER_ADC, 100);
        if (r != CAPTURE_OK) failure = capture_error(r);
        for (uint32_t j = 0; j < LOOP_FRAMES && !failure; ++j) {
            int32_t want = wave_buffer[wave_active][(j + LOOP_PERIOD - 5u) % LOOP_PERIOD] >> SYNCAVG_SHIFT;
            if (out.raw[2u * j] != want || out.raw[2u * j + 1u] != 0) failure = "loopback";
        }
    }
    /* Always restore: silence, normal DOUT, DAC powered. */
    if (!wave_silence() && !failure) failure = "stream_sync";
    if (!i2c_put(0, TAC_INTF_CFG1, TAC_DOUT_ASI) && !failure) failure = "codec_bus";
    if (tac5112_power(&codec, TAC_POWER_ALL) != TAC_OK && !failure) failure = "codec_power";
    return failure;
}

/* ---------------------------------------------------------------- range relays */
static void relay_put(void *context, unsigned pin, bool on) {
    (void)context;
    gpio_put(pin, on);
}
static const relay_io relays = {0, relay_put, io_sleep};
/* TQ2SA-L2 dual-coil latching relays (docs/rev-e-range-switching.md 3.2, src/relay.c): source
   silent, RESET all four for 20 ms, SET the range relay for 20 ms, SET K4 for 20 ms if
   `reference`, wait 10 ms, restore the source. Without `force` nothing switches if the source
   cannot be silenced; with it the relays switch anyway (boot and the end of REFCAPTURE, which
   must leave K4 open whatever else failed). */
static bool select_relays(int ohm, bool reference, bool force) {
    uint keep = wave_active;
    uint32_t keep_period = wave_period, keep_cycles = wave_cycles, keep_mv = wave_mv;
    bool silent = wave_silence();
    if (!silent && !force) return false;
    sleep_ms(5); /* codec filter delay and analog settling: contacts switch dry */
    if (!relay_select(&relays, (uint32_t)ohm, reference)) return false;
    sleep_ms(10);
    range_ohm = ohm;
    /* wave_silence wrote the other buffer, so the previous waveform is intact. */
    if (!wave_activate(keep, keep_period)) return false;
    wave_cycles = keep_cycles;
    wave_mv = keep_mv;
    return silent;
}
static bool select_range(int ohm) { return select_relays(ohm, false, false); }

/* ---------------------------------------------------------------- protocol 3 */
static uint32_t rail_sum(uint input) {
    adc_select_input(input);
    (void)adc_read();
    uint32_t sum = 0;
    for (uint i = 0; i < RAIL_SAMPLES; ++i) sum += adc_read();
    return sum;
}
static bool read_exact(uint8_t *buffer, size_t length) {
    for (size_t i = 0; i < length; ++i) {
        int c = getchar_timeout_us(200000);
        if (c == PICO_ERROR_TIMEOUT) return false;
        buffer[i] = (uint8_t)c;
    }
    return true;
}
/* After a failed upload, discard input until the line has been quiet for 200 ms so the
   rest of the binary payload is not parsed as commands. */
static void drain_input(void) {
    while (getchar_timeout_us(200000) != PICO_ERROR_TIMEOUT) {
    }
}
static void send_payload(const char *tag, uint32_t a, uint32_t b, const void *body, size_t body_bytes) {
    /* One CRC over the 16-byte header then the body. */
    uint32_t crc = wave_crc32_update(wave_crc32_update(0, header, sizeof header), body, body_bytes);
    printf("%s 3 %" PRIu32 " %" PRIu32 " %" PRIu32 "\n", tag, a, b, crc);
    stdio_put_string((const char *)header, (int)sizeof header, false, false);
    stdio_put_string((const char *)body, (int)body_bytes, false, false);
    puts("\nEND");
    stdio_flush();
}
static void process_command(const char *line) {
    uint32_t a = 0, b = 0, c = 0;
    char trailing;
    if (!strcmp(line, "INFO")) {
        printf("INFO 3 %s %s %u %u %u %d %" PRIu32 " %" PRIu32 " %" PRIu32 " %s\n", HARDWARE_REVISION,
               unit_id, SYSTEM_CLOCK_HZ, FS_HZ, WAVE_MAX_PERIOD, range_ohm, wave_period, wave_cycles,
               wave_mv, codec_ok ? "PASS" : "FAIL");
        return;
    }
    if (!strcmp(line, "OFF")) {
        puts(wave_silence() ? "OK" : "ERR stream_sync");
        return;
    }
    if (!strcmp(line, "RAILS")) {
        uint32_t mon12 = rail_sum(0), mon_n12 = rail_sum(1), die = rail_sum(4);
        printf("RAILS %u %" PRIu32 " %" PRIu32 " %" PRIu32 "\n", RAIL_SAMPLES, mon12, mon_n12, die);
        return;
    }
    if (!strcmp(line, "CODEC")) {
        static const uint8_t regs[] = {TAC_DEV_STS0, TAC_DEV_STS1, TAC_CLK_DET_STS0, TAC_CLK_ERR_STS0, TAC_CLK_ERR_STS1};
        printf("CODEC");
        for (unsigned i = 0; i < sizeof regs; ++i) {
            uint8_t v = 0;
            if (!i2c_get(0, regs[i], &v)) {
                puts(" ERR codec_bus");
                return;
            }
            printf(" %u", v);
        }
        puts("");
        return;
    }
    if (sscanf(line, "REG %" SCNu32 " %c", &a, &trailing) == 1) {
        uint8_t v = 0;
        if (a > 127u || !i2c_get(0, (uint8_t)a, &v)) puts("ERR codec_bus");
        else printf("REG %" PRIu32 " %u\n", a, v);
        return;
    }
    if (!strcmp(line, "BOOT")) {
        wave_silence();
        puts("OK");
        stdio_flush();
        sleep_ms(100);
        reset_usb_boot(0, 0);
        return;
    }
    if (!strcmp(line, "SELFTEST")) {
        const char *failure = selftest();
        codec_ok = failure == NULL;
        if (failure) printf("SELFTEST FAIL %s\n", failure);
        else puts("SELFTEST PASS");
        return;
    }
    if (sscanf(line, "RANGE %" SCNu32 " %c", &a, &trailing) == 1) {
        if (a != 100u && a != 5000u && a != 100000u) puts("ERR range");
        else puts(select_range((int)a) ? "OK" : "ERR stream_sync");
        return;
    }
    if (sscanf(line, "TONE %" SCNu32 " %" SCNu32 " %" SCNu32 " %c", &a, &b, &c, &trailing) == 3) {
        uint next = wave_active ^ 1u;
        wave_status st = wave_tone(wave_buffer[next], a, b, c);
        if (st != WAVE_OK) {
            memset(wave_buffer[next], 0, sizeof wave_buffer[next]);
            puts(st == WAVE_ERR_PERIOD ? "ERR period" : st == WAVE_ERR_FREQUENCY ? "ERR frequency" : "ERR level");
            return;
        }
        if (!wave_activate(next, b)) {
            puts("ERR stream_sync");
            return;
        }
        wave_cycles = a;
        wave_mv = c;
        puts("OK");
        return;
    }
    if (sscanf(line, "WAVE %" SCNu32 " %" SCNu32 " %c", &a, &b, &trailing) == 2) {
        uint next = wave_active ^ 1u;
        if (a < WAVE_MIN_PERIOD || a > WAVE_MAX_PERIOD) {
            puts("ERR period");
            return;
        }
        const char *error = NULL;
        if (!read_exact((uint8_t *)wave_buffer[next], 4u * a)) {
            drain_input();
            error = "ERR timeout";
        }
        else if (wave_crc32(wave_buffer[next], 4u * a) != b) error = "ERR crc";
        else if (wave_check(wave_buffer[next], a) != WAVE_OK) error = "ERR level";
        if (error) {
            memset(wave_buffer[next], 0, sizeof wave_buffer[next]);
            puts(error);
            return;
        }
        if (!wave_activate(next, a)) {
            puts("ERR stream_sync");
            return;
        }
        wave_cycles = wave_mv = 0;
        puts("OK");
        return;
    }
    bool raw = sscanf(line, "RAW %" SCNu32 " %c", &a, &trailing) == 1;
    bool avg = !raw && sscanf(line, "CAPTURE %" SCNu32 " %" SCNu32 " %c", &a, &b, &trailing) == 2;
    /* REFCAPTURE RANGE SKIP PERIODS: CAPTURE of the internal 1 kOhm reference (K4) on RANGE. */
    bool ref = !raw && !avg &&
               sscanf(line, "REFCAPTURE %" SCNu32 " %" SCNu32 " %" SCNu32 " %c", &c, &a, &b, &trailing) == 3;
    if (!raw && !avg && !ref) {
        puts("ERR command");
        return;
    }
    if (ref && relay_set_pin(c) == 0u) {
        puts("ERR range");
        return;
    }
    /* RAW COUNT: COUNT consecutive frames. CAPTURE SKIP PERIODS: skip SKIP whole periods,
       then sum PERIODS periods into one bin per waveform index. At most 60 s of frames. */
    uint64_t frames = raw ? a : (uint64_t)b * wave_period;
    uint64_t skip = raw ? 0u : (uint64_t)a * wave_period;
    if (!codec_ok || !gpio_get(PIN_USB_VBUS) || frames == 0u ||
        (raw && frames > RAW_MAX_FRAMES) || skip + frames > 60u * (uint64_t)FS_HZ) {
        puts("ERR limits_or_selftest");
        return;
    }
    /* The reference relay is closed only here, together with one range relay, and opened
       again (RESET, then the range that was selected before) before the reply. */
    int restore = range_ohm ? range_ohm : (int)c;
    if (ref && !select_relays((int)c, true, false)) {
        select_relays(restore, false, true);
        puts("ERR stream_sync");
        return;
    }
    syncavg_t s;
    if (raw) syncavg_init_raw(&s, out.raw, (uint32_t)frames);
    else syncavg_init_average(&s, out.sum, wave_period, (uint32_t)frames);
    gpio_put(PIN_LED, true);
    capture_result r = capture(&s, (uint32_t)skip, TAC_POWER_ALL,
                               (uint32_t)((skip + frames) * 1000u / FS_HZ) + 100u);
    gpio_put(PIN_LED, false);
    if (ref && !select_relays(restore, false, true) && r == CAPTURE_OK) r = CAPTURE_SYNC;
    if (r != CAPTURE_OK) {
        codec_ok = false;
        printf("ERR %s\n", capture_error(r));
        return;
    }
    if (raw) send_payload("RAW", (uint32_t)frames, 0, out.raw, 8u * (size_t)frames);
    else send_payload("DATA", wave_period, b, out.sum, 16u * (size_t)wave_period);
}

int main(void) {
    set_sys_clock_khz(SYSTEM_CLOCK_HZ / 1000u, true);
    gpio_init(PIN_LED);
    gpio_set_dir(PIN_LED, GPIO_OUT);
    const uint relay_pins[] = {PIN_RNG_RESET, PIN_RNG_SET_LO, PIN_RNG_SET_MED, PIN_RNG_SET_HI, PIN_RNG_SET_REF};
    for (unsigned i = 0; i < sizeof relay_pins / sizeof relay_pins[0]; ++i) {
        gpio_init(relay_pins[i]);
        gpio_put(relay_pins[i], false);
        gpio_set_dir(relay_pins[i], GPIO_OUT);
    }
    gpio_init(PIN_USB_VBUS);
    gpio_set_dir(PIN_USB_VBUS, GPIO_IN);
    adc_init();
    adc_gpio_init(PIN_MON12);
    adc_gpio_init(PIN_MON_N12);
    adc_set_temp_sensor_enabled(true);
    pico_get_unique_board_id_string(unit_id, sizeof(unit_id));
    i2c_init(i2c0, 400000);
    gpio_set_function(PIN_I2C_SDA, GPIO_FUNC_I2C);
    gpio_set_function(PIN_I2C_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(PIN_I2C_SDA);
    gpio_pull_up(PIN_I2C_SCL);
    tdm_sm = pio_claim_unused_sm(tdm_pio, true);
    ch_txd = dma_claim_unused_channel(true);
    ch_txc = dma_claim_unused_channel(true);
    ch_snap = dma_claim_unused_channel(true);
    ch_rxd = dma_claim_unused_channel(true);
    stream_start(); /* silent waveform, clocks running before the codec is configured */
    sleep_ms(5);    /* codec POR: 2 ms after the supplies */
    codec_ok = tac5112_start(&codec) == TAC_OK && selftest() == NULL;
    /* Relays keep their state through power-off (K4 too, if power failed during a
       REFCAPTURE): always RESET all four and start on the 100 kOhm range, K4 open. */
    if (!select_relays(100000, false, true)) codec_ok = false;
    while (!gpio_get(PIN_USB_VBUS)) tight_loop_contents();
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false);
    char line[96];
    uint length = 0;
    bool overflow = false;
    while (true) {
        if (!gpio_get(PIN_USB_VBUS)) {
            wave_silence();
            tud_disconnect();
            while (!gpio_get(PIN_USB_VBUS)) sleep_ms(10);
            tud_connect();
            length = 0;
            overflow = false;
        }
        int ch = getchar_timeout_us(10000);
        if (ch == PICO_ERROR_TIMEOUT || ch == '\r') continue;
        if (ch == '\n') {
            line[length] = '\0';
            if (overflow) puts("ERR line_too_long");
            else process_command(line);
            length = 0;
            overflow = false;
        } else if (length + 1u < sizeof(line)) {
            line[length++] = (char)ch;
        } else overflow = true;
    }
}
