#include "pins.h"
#include "fast_spi.h"
#include "fast_capture.h"
#include "driver/spi_master.h"
#include "esp_timer.h"
static spi_device_handle_t capture;
static fast_capture_receiver_t receiver;
bool r5_fast_init(void)
{
    spi_bus_config_t bus={.mosi_io_num=R5_FAST_MOSI,.miso_io_num=R5_FAST_MISO,
      .sclk_io_num=R5_FAST_CLK,.quadwp_io_num=-1,.quadhd_io_num=-1,.max_transfer_sz=FAST_CAPTURE_BYTES};
    if(spi_bus_initialize(SPI2_HOST,&bus,SPI_DMA_CH_AUTO)!=ESP_OK) return false;
    spi_device_interface_config_t device={.clock_speed_hz=10000000,.mode=0,
      .spics_io_num=R5_FAST_CS,.queue_size=1};
    return spi_bus_add_device(SPI2_HOST,&device,&capture)==ESP_OK;
}
bool r5_fast_sample(bridge_feedback_t *out)
{
    if(!capture || !out) return false;
    uint8_t rx[FAST_CAPTURE_BYTES],tx[FAST_CAPTURE_BYTES]={0};
    spi_transaction_t t={.length=FAST_CAPTURE_BYTES*8,.rx_buffer=rx,.tx_buffer=tx};
    uint32_t at=(uint32_t)esp_timer_get_time();
    if(spi_device_polling_transmit(capture,&t)!=ESP_OK) {
        receiver.fault=true; *out=(bridge_feedback_t){0}; return false;
    }
    return fast_capture_accept(&receiver,rx,sizeof rx,at,(uint32_t)esp_timer_get_time(),out);
}
