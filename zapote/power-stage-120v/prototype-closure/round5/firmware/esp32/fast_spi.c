#include "pins.h"
#include "bench_pins.h"
#include "fast_spi.h"
#include "fast_capture.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
static spi_device_handle_t capture;
static fast_capture_receiver_t receiver;
static uint32_t previous_end;
static bool have_transaction;
static bool released;
static int64_t held_since;
bool r5_fast_init(void)
{
    if(capture) return false; /* A runtime re-init must not erase sequence history. */
    gpio_set_level(R5_FAST_RESET_N,0);
    gpio_config_t reset={.pin_bit_mask=1ULL<<R5_FAST_RESET_N,.mode=GPIO_MODE_OUTPUT,.pull_down_en=true};
    gpio_config_t fault={.pin_bit_mask=1ULL<<R5_FAST_FAULT,.mode=GPIO_MODE_INPUT,.pull_up_en=true};
    if(gpio_config(&reset)!=ESP_OK||gpio_config(&fault)!=ESP_OK) return false;
    held_since=esp_timer_get_time();
    spi_bus_config_t bus={.mosi_io_num=R5_FAST_MOSI,.miso_io_num=R5_FAST_MISO,
      .sclk_io_num=R5_FAST_CLK,.quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=FAST_CAPTURE_BYTES};
    if(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_CH_AUTO)!=ESP_OK) return false;
    spi_device_interface_config_t device={.clock_speed_hz=5000000,.mode=0,
      .spics_io_num=R5_FAST_CS,.queue_size=1,.cs_ena_pretrans=1,
      .flags=SPI_DEVICE_HALFDUPLEX};
    return spi_bus_add_device(SPI2_HOST,&device,&capture)==ESP_OK;
}
bool r5_fast_release_reset(bool qualified)
{
    if(!qualified||!capture||released||receiver.fault||gpio_get_level(R5_REQUEST)) return false;
    /*10ms oscillator allowance exceeds selected oscillator's5ms maximum.
      With unqualified clock/waveforms this entry point is never called true. */
    int64_t held=esp_timer_get_time()-held_since;
    if(held<10000) esp_rom_delay_us((uint32_t)(10000-held));
    if(gpio_set_level(R5_FAST_RESET_N,1)!=ESP_OK) return false;
    esp_rom_delay_us(200);released=true;return true;
}
bool r5_fast_sample(bridge_feedback_t *out)
{
    if(!capture || !out) return false;
    if(!released) { *out=(bridge_feedback_t){0};return false; }
    if(gpio_get_level(R5_FAST_FAULT)) {
        receiver.fault=true;*out=(bridge_feedback_t){0};return false;
    }
    /* RX-only half-duplex honors ESP-IDF's documented CS setup feature;
       exactly736 clocks,200ns setup and at least2us idle between reads. */
    uint8_t rx[FAST_CAPTURE_BYTES];
    spi_transaction_t t={.rxlength=FAST_CAPTURE_BYTES*8,.rx_buffer=rx};
    uint32_t at=(uint32_t)esp_timer_get_time();
    if(have_transaction&&(uint32_t)(at-previous_end)<2) {
        receiver.fault=true;*out=(bridge_feedback_t){0};return false;
    }
    if(spi_device_polling_transmit(capture,&t)!=ESP_OK) {
        receiver.fault=true; *out=(bridge_feedback_t){0}; return false;
    }
    previous_end=(uint32_t)esp_timer_get_time();have_transaction=true;
    return fast_capture_accept(&receiver,rx,sizeof rx,at,previous_end,out);
}
