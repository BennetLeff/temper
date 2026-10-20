#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "pico/unique_id.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "tusb.h"
#include "pins.h"
#include "capture.pio.h"

static uint32_t samples[MAX_SAMPLES];
static PIO adc_pio = pio0;
static uint adc_sm, adc_offset;
static int adc_dma;
static bool adc_ok = false;
static char unit_id[PICO_UNIQUE_BOARD_ID_SIZE_BYTES * 2 + 1];

static void output_pin(uint pin, bool high) {
    gpio_init(pin);
    gpio_put(pin, high);
    gpio_set_dir(pin, GPIO_OUT);
}
static void adc_idle(void) {
    pio_sm_set_enabled(adc_pio, adc_sm, false);
    output_pin(PIN_ADC_CS, true);
    output_pin(PIN_ADC_SCLK, false);
    output_pin(PIN_ADC_CONVST, false);
}
/* Slow mode-0 command transaction. Conversion results are read by PIO. */
static void adc_command(uint16_t command) {
    adc_idle();
    gpio_put(PIN_ADC_CS, false);
    sleep_us(1);
    for (int bit = 15; bit >= 0; --bit) {
        gpio_put(PIN_ADC_SDI, (command >> bit) & 1u);
        sleep_us(1);
        gpio_put(PIN_ADC_SCLK, true);
        sleep_us(1);
        gpio_put(PIN_ADC_SCLK, false);
    }
    sleep_us(1);
    gpio_put(PIN_ADC_CS, true);
    gpio_put(PIN_ADC_SDI, false); /* NOP0 during conversion frames */
    sleep_us(1);
}
/* AD9833 clocks SDATA on falling SCLK; FSYNC stays low for 16 bits. */
static void dds_word(uint16_t word) {
    gpio_put(PIN_DDS_SCLK, true);
    gpio_put(PIN_DDS_FSYNC, false);
    sleep_us(1);
    for (int bit = 15; bit >= 0; --bit) {
        gpio_put(PIN_DDS_DATA, (word >> bit) & 1u);
        sleep_us(1);
        gpio_put(PIN_DDS_SCLK, false);
        sleep_us(1);
        gpio_put(PIN_DDS_SCLK, true);
    }
    gpio_put(PIN_DDS_FSYNC, true);
    sleep_us(1);
}
static void dds_off(void) { dds_word(0x21c0u); } /* RESET + both SLEEP bits */
static void dds_start(uint32_t word) {
    dds_word(0x2100u); /* B28 + RESET */
    dds_word((uint16_t)(0x4000u | (word & 0x3fffu)));
    dds_word((uint16_t)(0x4000u | ((word >> 14) & 0x3fffu)));
    dds_word(0xc000u); /* phase register zero */
    dds_word(0x2000u); /* sine, DAC enabled, phase accumulator running */
}
static uint16_t channel_bits(uint32_t packed, uint channel) {
    uint16_t result = 0;
    for (uint bit = 0; bit < 16; ++bit)
        result |= ((packed >> (2u * bit + channel)) & 1u) << bit;
    return result;
}
static uint32_t crc32(const void *buffer, size_t length) {
    const uint8_t *p = buffer;
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; ++i) {
        crc ^= p[i];
        for (uint bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
static bool capture(uint divider, uint count) {
    adc_idle();
    dma_channel_abort(adc_dma);
    pio_sm_clear_fifos(adc_pio, adc_sm);
    pio_interrupt_clear(adc_pio, 0);
    pio_interrupt_clear(adc_pio, 4);
    adc_pio->fdebug = (1u << (PIO_FDEBUG_RXSTALL_LSB + adc_sm));
    for (uint pin = PIN_ADC_A; pin <= PIN_ADC_CONVST; ++pin)
        pio_gpio_init(adc_pio, pin);
    pio_sm_config config = capture_program_get_default_config(adc_offset);
    sm_config_set_in_pins(&config, PIN_ADC_A);
    sm_config_set_jmp_pin(&config, PIN_ADC_READY);
    sm_config_set_sideset_pins(&config, PIN_ADC_CS);
    sm_config_set_in_shift(&config, false, true, 32);
    sm_config_set_clkdiv_int_frac(&config, divider, 0);
    pio_sm_init(adc_pio, adc_sm, adc_offset, &config);
    pio_sm_put(adc_pio, adc_sm, count - 1u);
    pio_sm_set_consecutive_pindirs(adc_pio, adc_sm, PIN_ADC_A, 2, false);
    pio_sm_set_consecutive_pindirs(adc_pio, adc_sm, PIN_ADC_CS, 3, true);
    adc_pio->input_sync_bypass |= (1u << PIN_ADC_A) | (1u << PIN_ADC_B);
    dma_channel_config dma = dma_channel_get_default_config(adc_dma);
    channel_config_set_transfer_data_size(&dma, DMA_SIZE_32);
    channel_config_set_read_increment(&dma, false);
    channel_config_set_write_increment(&dma, true);
    channel_config_set_dreq(&dma, pio_get_dreq(adc_pio, adc_sm, false));
    dma_channel_configure(adc_dma, &dma, samples, &adc_pio->rxf[adc_sm], count, true);
    pio_sm_set_enabled(adc_pio, adc_sm, true);
    absolute_time_t deadline = make_timeout_time_ms(100u + (count * divider) / 1000u);
    bool failed = false;
    while (!pio_interrupt_get(adc_pio, 0)) {
        if (pio_interrupt_get(adc_pio, 4) || time_reached(deadline)) {
            failed = true;
            break;
        }
        tight_loop_contents();
    }
    /* A FIFO stall would corrupt the sample timebase. PIO stops after exactly
       count frames, so a sticky stall cannot be an after-capture false alarm. */
    if ((adc_pio->fdebug & (1u << (PIO_FDEBUG_RXSTALL_LSB + adc_sm))) ||
        dma_channel_is_busy(adc_dma))
        failed = true;
    adc_idle();
    dma_channel_abort(adc_dma);
    return !failed;
}
static bool adc_selftest(void) {
    adc_command(0x1502u); /* OUTPUT_DATA_WORD_CFG: fixed A55A on both ADCs */
    if (!capture(1, 256)) {
        adc_command(0x1500u);
        return false;
    }
    bool pass = true;
    for (uint i = 0; i < 256; ++i)
        if (channel_bits(samples[i], 0) != 0xa55au ||
            channel_bits(samples[i], 1) != 0xa55au)
            pass = false;
    adc_command(0x1500u);
    return pass;
}
static void process_command(const char *line) {
    if (!strcmp(line, "INFO")) {
        printf("INFO 1 B %s %u %u %u %u %s\n", unit_id, SYSTEM_CLOCK_HZ,
               DDS_CLOCK_HZ, CAPTURE_CYCLES, MAX_SAMPLES, adc_ok ? "PASS" : "FAIL");
        return;
    }
    if (!strcmp(line, "OFF")) {
        dds_off();
        puts("OK");
        return;
    }
    if (!strcmp(line, "SELFTEST")) {
        dds_off();
        adc_ok = adc_selftest();
        puts(adc_ok ? "SELFTEST PASS" : "SELFTEST FAIL");
        return;
    }
    uint32_t word = 0;
    uint divider = 0, count = 0;
    char trailing;
    bool source_off = !strncmp(line, "NOISE ", 6);
    const char *arguments = source_off ? line + 6 :
        (!strncmp(line, "CAPTURE ", 8) ? line + 8 : "");
    if (sscanf(arguments, "%" SCNu32 " %u %u %c", &word, &divider, &count, &trailing) != 3) {
        puts("ERR command");
        return;
    }
    /* 100 Hz <= frequency <= 100 kHz; integer divider 1..20.
       At least 8 samples/cycle, and >= 10 cycles in the capture. */
    double frequency = (double)word * DDS_CLOCK_HZ / 268435456.0;
    double rate = divider ? 1000000.0 / divider : 0.0;
    if (!adc_ok || !gpio_get(PIN_USB_VBUS) || word == 0 || divider == 0 || divider > 20 ||
        count < 256 || count > MAX_SAMPLES || frequency < 99.9 || frequency > 100000.1 ||
        rate < 8.0 * frequency || (double)count * frequency / rate < 10.0) {
        puts("ERR limits_or_selftest");
        return;
    }
    if (source_off) dds_off();
    else dds_start(word);
    gpio_put(PIN_LED, true);
    /* RC coupling + coil transient settling. Twenty cycles, at least 1000 ms. */
    uint settle_ms = (uint)(20000.0 / frequency) + 1u;
    if (settle_ms < 1000) settle_ms = 1000;
    sleep_ms(settle_ms);
    bool success = capture(divider, count);
    dds_off();
    gpio_put(PIN_LED, false);
    if (!success) {
        adc_ok = false;
        puts("ERR acquisition_timing");
        return;
    }
    uint32_t crc = crc32(samples, count * sizeof(samples[0]));
    printf("%s 1 %" PRIu32 " %u %u %" PRIu32 "\n",
           source_off ? "NOISE" : "DATA", word, divider, count, crc);
    stdio_put_string((const char *)samples, (int)(count * sizeof(samples[0])), false, false);
    puts("\nEND");
    stdio_flush();
}
int main(void) {
    set_sys_clock_khz(SYSTEM_CLOCK_HZ / 1000u, true);
    clock_gpio_init(PIN_DDS_MCLK, CLOCKS_CLK_GPOUT0_CTRL_AUXSRC_VALUE_CLK_SYS, 5.0f);
    output_pin(PIN_LED, false);
    output_pin(PIN_ADC_CS, true);
    output_pin(PIN_ADC_SCLK, false);
    output_pin(PIN_ADC_CONVST, false);
    output_pin(PIN_ADC_SDI, false);
    output_pin(PIN_ADC_RESET, false);
    output_pin(PIN_DDS_FSYNC, true);
    output_pin(PIN_DDS_SCLK, true);
    output_pin(PIN_DDS_DATA, false);
    gpio_init(PIN_ADC_READY);
    gpio_set_dir(PIN_ADC_READY, GPIO_IN);
    gpio_init(PIN_USB_VBUS);
    gpio_set_dir(PIN_USB_VBUS, GPIO_IN);
    pico_get_unique_board_id_string(unit_id, sizeof(unit_id));
    adc_sm = pio_claim_unused_sm(adc_pio, true);
    adc_offset = pio_add_program(adc_pio, &capture_program);
    adc_dma = dma_claim_unused_channel(true);
    sleep_us(10);
    gpio_put(PIN_ADC_RESET, true);
    sleep_ms(200); /* Reference settling max 150 ms, SBAS876C table 6.9. */
    dds_off();
    adc_ok = adc_selftest();
    while (!gpio_get(PIN_USB_VBUS)) tight_loop_contents();
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false);
    char line[96];
    uint length = 0;
    bool overflow = false;
    while (true) {
        if (!gpio_get(PIN_USB_VBUS)) {
            dds_off();
            tud_disconnect();
            while (!gpio_get(PIN_USB_VBUS)) sleep_ms(10);
            tud_connect();
            length = 0;
            overflow = false;
        }
        int c = getchar_timeout_us(10000);
        if (c == PICO_ERROR_TIMEOUT) continue;
        if (c == '\r') continue;
        if (c == '\n') {
            line[length] = '\0';
            if (overflow) puts("ERR line_too_long");
            else process_command(line);
            length = 0;
            overflow = false;
        } else if (length + 1u < sizeof(line)) {
            line[length++] = (char)c;
        } else overflow = true;
    }
}
