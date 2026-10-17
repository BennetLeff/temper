#include "mcpwm_target.h"
#include "fast_spi.h"
#include "pins.h"
#include "energy_link.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
void app_main(void)
{
    gpio_config_t pins={.pin_bit_mask=(1ULL<<R5_REQUEST)|(1ULL<<R5_HEARTBEAT)|(1ULL<<R5_FAULT_HIGH)|
      (1ULL<<R5_RAIL_OK)|(1ULL<<R5_INTERLOCK_OK),.mode=GPIO_MODE_OUTPUT};
    if(gpio_config(&pins)!=ESP_OK) return;
    gpio_set_level(R5_REQUEST,0); gpio_set_level(R5_FAULT_HIGH,1);
    gpio_set_level(R5_RAIL_OK,0); gpio_set_level(R5_INTERLOCK_OK,0); gpio_set_level(R5_HEARTBEAT,0);
    uart_config_t uc={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,
      .stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    if(uart_param_config(UART_NUM_1,&uc)!=ESP_OK ||
       uart_set_pin(UART_NUM_1,R5_UART_TX,R5_UART_RX,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE)!=ESP_OK ||
       uart_driver_install(UART_NUM_1,256,0,0,NULL,0)!=ESP_OK) return;
    bridge_backend_t backend;
    bool initialized=r5_pwm_init(&backend);
    bool capture_initialized=r5_fast_init();
    energy_link_receiver_t receiver={0};
    uint32_t seq=0; uint8_t rx[ENERGY_LINK_SIZE]; unsigned count=0;
    for(;;) {
        /* Bench-only acquisition. This 5 ms polling cadence cannot grant the
           production <=1 ms capture freshness requirement. */
        bridge_feedback_t feedback;
        if(capture_initialized && !r5_fast_sample(&feedback) && initialized)
            backend.inhibit(backend.context);
        /* Bench-only diagnostic status. Never assert rails, interlock or request. */
        energy_link_packet_t tx={.kind=ENERGY_LINK_COMMAND,.state=0,.flags=ENERGY_LINK_FAULT,.sequence=++seq};
        uint8_t frame[ENERGY_LINK_SIZE];
        if(!energy_link_encode(&tx,frame) || uart_write_bytes(UART_NUM_1,frame,sizeof frame)!=(int)sizeof frame) {
            if(initialized) backend.inhibit(backend.context);
        }
        int got=uart_read_bytes(UART_NUM_1,rx+count,sizeof rx-count,0);
        if(got>0) count+=(unsigned)got;
        if(count==sizeof rx) {
            energy_link_packet_t status;
            if(!energy_link_receive(&receiver,ENERGY_LINK_STATUS,rx,sizeof rx,(uint32_t)(esp_timer_get_time()/1000),&status)) {
                if(initialized) backend.inhibit(backend.context);
            }
            count=0;
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}
