#include "mcpwm_target.h"
#include "power_target.h"
#include "pins.h"
#include "energy_link.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static TaskHandle_t owner;
static void wake(void *unused) { (void)unused;xTaskNotifyGive(owner); }
void app_main(void)
{
    gpio_config_t pins={.pin_bit_mask=(1ULL<<R5_REQUEST)|(1ULL<<R5_HEARTBEAT)|(1ULL<<R5_FAULT_HIGH)|
      (1ULL<<R5_RAIL_OK)|(1ULL<<R5_INTERLOCK_OK),.mode=GPIO_MODE_OUTPUT};
    if(gpio_config(&pins)!=ESP_OK) return;
    gpio_set_level(R5_REQUEST,0);gpio_set_level(R5_FAULT_HIGH,1);
    gpio_set_level(R5_RAIL_OK,0);gpio_set_level(R5_INTERLOCK_OK,0);gpio_set_level(R5_HEARTBEAT,0);
    pins=(gpio_config_t){.pin_bit_mask=1ULL<<R5_SUP_RUN_OK,.mode=GPIO_MODE_INPUT,.pull_down_en=true};
    if(gpio_config(&pins)!=ESP_OK) return;
    uart_config_t uc={.baud_rate=115200,.data_bits=UART_DATA_8_BITS,.parity=UART_PARITY_DISABLE,
      .stop_bits=UART_STOP_BITS_1,.flow_ctrl=UART_HW_FLOWCTRL_DISABLE,.source_clk=UART_SCLK_DEFAULT};
    if(uart_param_config(UART_NUM_1,&uc)!=ESP_OK||
       uart_set_pin(UART_NUM_1,R5_UART_TX,R5_UART_RX,UART_PIN_NO_CHANGE,UART_PIN_NO_CHANGE)!=ESP_OK||
       uart_driver_install(UART_NUM_1,256,0,0,NULL,0)!=ESP_OK) return;
    static r5_power_context_t context; /* No factory records/providers are installed by this image. */
    bridge_backend_t backend;
    if(!r5_pwm_init(&backend,context.commissioned)) return;
    power_service_bootstrap();
    /* Actual binding is installed here. The shared service rejects the false
       commissioning flag, preserving physical inhibition in this build. */
    bool bound=r5_power_bind(&context,&backend);
    if(bound&&!r5_pwm_prepare_capture(context.boot_inhibit_verified)) { backend.inhibit(backend.context);return; }
    energy_link_receiver_t receiver={0};
    bool heartbeat_level=false,service_started=false;uint32_t seq=0,last_tx=0,last_wake=0;uint8_t rx[R5_LINE_BYTES];unsigned count=0,length=0;
    owner=xTaskGetCurrentTaskHandle();vTaskPrioritySet(owner,configMAX_PRIORITIES-2);
    esp_timer_handle_t timer;
    esp_timer_create_args_t args={.callback=wake,.name="power250us"};
    if(esp_timer_create(&args,&timer)!=ESP_OK||esp_timer_start_periodic(timer,250)!=ESP_OK) {
        backend.inhibit(backend.context);return;
    }
    for(;;) {
        ulTaskNotifyTake(pdTRUE,portMAX_DELAY);
        uint32_t us=(uint32_t)esp_timer_get_time();
        if(last_wake&&(uint32_t)(us-last_wake)>1000) backend.inhibit(backend.context);
        last_wake=us;
        /* Byte framing selects exact legacy20 or TLM1/28 bytes. Corruption
           inhibits immediately; no corrupted telemetry is promoted to valid. */
        uint8_t byte;
        while(uart_read_bytes(UART_NUM_1,&byte,1,0)==1) {
            if(!count&&byte!='T') { backend.inhibit(backend.context);continue; }
            rx[count++]=byte;
            if(count==2) {
                length=byte=='E'?ENERGY_LINK_SIZE:byte=='L'?R5_LINE_BYTES:0;
                if(!length) { count=0;backend.inhibit(backend.context); }
            }
            if(length&&count==length) {
                bool ok;
                if(length==R5_LINE_BYTES) ok=r5_line_receive(&context.line,rx,us);
                else {
                    energy_link_packet_t status;
                    ok=energy_link_receive(&receiver,ENERGY_LINK_STATUS,rx,length,us/1000,&status);
                    if(ok&&(status.flags&ENERGY_LINK_FAULT)) backend.inhibit(backend.context);
                }
                if(!ok) backend.inhibit(backend.context);
                count=0;length=0;
            }
        }
        if(bound&&(service_started||(context.line.seen&&context.rails_qualified&&context.interlock_qualified&&!context.bus_fault))) {
            service_started=true;power_service_tick(); /* Once started, loss of any qualifier is a latched fault. */
        }
        if((uint32_t)(us-last_tx)>=5000) {
            last_tx=us;
            bool healthy=bound&&test_pwm_generation()&&context.rails_qualified&&context.interlock_qualified&&!context.bus_fault;
            gpio_set_level(R5_FAULT_HIGH,!healthy);
            gpio_set_level(R5_RAIL_OK,healthy&&context.rails_qualified);
            gpio_set_level(R5_INTERLOCK_OK,healthy&&context.interlock_qualified);
            energy_link_packet_t tx={.kind=ENERGY_LINK_COMMAND,.flags=healthy?
                (ENERGY_LINK_RAIL_OK|(r5_pwm_requested()?ENERGY_LINK_REQUEST:0)):ENERGY_LINK_FAULT,.sequence=++seq};
            uint8_t frame[ENERGY_LINK_SIZE];
            if(!energy_link_encode(&tx,frame)||uart_tx_chars(UART_NUM_1,(const char *)frame,sizeof frame)!=(int)sizeof frame)
                backend.inhibit(backend.context);
            heartbeat_level=healthy?!heartbeat_level:false;
            gpio_set_level(R5_HEARTBEAT,heartbeat_level);
        }
    }
}
