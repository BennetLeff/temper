/* STM32G071RBT6 round4 supervisor pin contract. CMSIS device header from ST. */
#include "stm32g071xx.h"
#include "acquisition.h"
#include "qualification.h"
#include "sensor_frontend.h"
#include "line_telemetry.h"
#include "mirror.h"
#include "bypass.h"
#include "supervisor_outputs.h"
#include "energy_link.h"
#include "controller_intent.h"
#include <stdbool.h>
#include <stdint.h>
uint32_t SystemCoreClock = 16000000;
static volatile uint32_t drdy_at,drdy_ms;
static volatile bool drdy_pending, acquisition_overrun;
static volatile uint32_t milliseconds;
static uint8_t uart_rx[ENERGY_LINK_SIZE];
static unsigned uart_used;
static uint8_t uart_tx[R5_LINE_BYTES];
static unsigned uart_sent,uart_length;
static uint8_t line_tx[R5_LINE_BYTES];
static bool line_pending;
static uint32_t uart_sequence, uart_started;
static volatile uint16_t ntc_raw[2];
static bool ntc_ok;
static uint32_t ntc_sampled;
static energy_link_receiver_t link;
static energy_link_packet_t command;
static ads_receiver_t adc;
static r5_supervisor_t binding;
#define supervisor binding.energy
static post_record_t post;
static r5_heartbeat_t heartbeat;
static r5_sensor_frontend_t sensors;
static r5_mirror_t mirrors,mirror_scan;
static volatile bool mirror_all_off,mirror_discharged;
static bool bypass_proven;
static void mode(GPIO_TypeDef *p, unsigned n, unsigned m)
{ p->MODER = (p->MODER & ~(3u << (n*2))) | (m << (n*2)); }
static void af(GPIO_TypeDef *p, unsigned n, unsigned a)
{ p->AFR[n/8] = (p->AFR[n/8] & ~(15u << ((n%8)*4))) | (a << ((n%8)*4)); mode(p,n,2); }
static void out(GPIO_TypeDef *p, unsigned n, bool high)
{ p->BSRR = 1u << (n + (high ? 0 : 16)); }
static bool pin(GPIO_TypeDef *p, unsigned n) { return (p->IDR & (1u<<n)) != 0; }
static uint32_t micros(void) { return TIM2->CNT; }
void SystemInit(void) { /* No C data access before runtime initialization. */ }
void SysTick_Handler(void) { ++milliseconds; }
void EXTI0_1_IRQHandler(void)
{
    if (EXTI->FPR1 & 1u) {
        EXTI->FPR1 = 1u;
        if (drdy_pending) acquisition_overrun = true;
        drdy_at = micros(); drdy_ms=milliseconds; drdy_pending = true;
    }
}
static void safe_outputs(void)
{
    /* Drop MCU_RUN first; independently wired hardware faults still dominate. */
    out(GPIOB,14,false);
    out(GPIOC,15,false);
    out(GPIOD,4,false);
    out(GPIOD,8,false);out(GPIOD,9,false);
    GPIOC->BSRR = ((1u<<4)|(1u<<5)|(1u<<6)) << 16;
    GPIOB->BSRR = ((1u<<0)|(1u<<1)|(1u<<2)|(1u<<10)|(1u<<11)|(1u<<12)|(1u<<13)) << 16;
    out(GPIOB,15,true);
}
void r5_fault_shutdown(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOBEN|RCC_IOPENR_GPIOCEN|RCC_IOPENR_GPIODEN;
    (void)RCC->IOPENR;
    safe_outputs();
    /* Stop feeding WDI. Independent hardware timeout/reset remains active. */
    for(;;) {}
}
/* TIM3 owns receiver excitation/sampling. ADC SPI polling can no longer delay
   the 50us mirror schedule. Main only copies a coherent published snapshot. */
void TIM3_IRQHandler(void)
{
    TIM3->SR=0;
    uint32_t us=micros();unsigned previous_mask=mirror_scan.excite_mask;
    bool r[R5_MIRROR_MAX]={pin(GPIOC,7),pin(GPIOC,8),pin(GPIOC,9),pin(GPIOC,13),pin(GPIOC,14)};
    (void)r5_mirror_step(&mirror_scan,us,r,mirror_all_off,mirror_discharged);
    if(mirror_all_off&&mirror_discharged&&!mirror_scan.static_requested)
        (void)r5_mirror_hold_static(&mirror_scan,us);
    for(unsigned n=0;n<3;n++) out(GPIOD,n,(mirror_scan.excite_mask&(1u<<n))!=0);
    out(GPIOA,12,(mirror_scan.excite_mask&8)!=0);out(GPIOA,15,(mirror_scan.excite_mask&16)!=0);
    /* Settling starts after the last actual GPIO write, not ISR entry. */
    if(previous_mask!=mirror_scan.excite_mask) mirror_scan.slot_at=micros();
}
static void mirror_timer_init(void)
{
    (void)r5_mirror_init(&mirror_scan,5);
    RCC->APBENR1|=RCC_APBENR1_TIM3EN;TIM3->PSC=15;TIM3->ARR=49;
    TIM3->EGR=1;TIM3->SR=0;TIM3->DIER=TIM_DIER_UIE;
    NVIC_SetPriority(TIM3_IRQn,1);NVIC_EnableIRQ(TIM3_IRQn);TIM3->CR1=1;
}
static bool wait_mask(
volatile uint32_t *reg, uint32_t mask, bool set, uint32_t bound)
{
    while (((*reg & mask) != 0) != set) if (!bound--) return false;
    return true;
}
static bool hardware_init(void)
{
    RCC->CR |= RCC_CR_HSION;
    if (!wait_mask(&RCC->CR,RCC_CR_HSIRDY,true,100000)) return false;
    RCC->CR &= ~RCC_CR_HSIDIV;
    RCC->CFGR = 0; /* HSI16 SYSCLK, HCLK, PCLK all 16 MHz. */
    if (!wait_mask(&RCC->CFGR,RCC_CFGR_SWS,false,100000)) return false;
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN|RCC_IOPENR_GPIOBEN|RCC_IOPENR_GPIOCEN|RCC_IOPENR_GPIODEN;
    (void)RCC->IOPENR;
    const unsigned b_outputs[] = {0,1,2,10,11,12,13,14,15};
    safe_outputs();
    for (unsigned i=0;i<sizeof b_outputs/sizeof b_outputs[0];++i) mode(GPIOB,b_outputs[i],1);
    for (unsigned i=3;i<=6;++i) mode(GPIOC,i,1);
    for (unsigned i=0;i<=2;++i) { out(GPIOD,i,false); mode(GPIOD,i,1); }
    out(GPIOD,8,false);mode(GPIOD,8,1);out(GPIOD,9,false);mode(GPIOD,9,1);
    out(GPIOA,12,false);mode(GPIOA,12,1);out(GPIOA,15,false);mode(GPIOA,15,1);
    out(GPIOC,15,false);mode(GPIOC,15,1);
    const unsigned a_inputs[]={0,11};
    for(unsigned i=0;i<2;++i) mode(GPIOA,a_inputs[i],0);
    for(unsigned i=3;i<=9;++i) mode(GPIOB,i,0);
    const unsigned c_inputs[]={0,1,2,7,8,9,10,11,12,13,14};
    for(unsigned i=0;i<sizeof c_inputs/sizeof c_inputs[0];++i) mode(GPIOC,c_inputs[i],0);
    for(unsigned i=3;i<=6;++i) mode(GPIOD,i,0);
    out(GPIOD,4,false); mode(GPIOD,4,1); /* qualified heartbeat permissive */
    /* PA2/PA3 remain analog for resistor NTC acquisition. SWD PA13/14 untouched. */
    mode(GPIOA,2,3); mode(GPIOA,3,3);
    out(GPIOA,1,false); mode(GPIOA,1,1); out(GPIOA,4,true); mode(GPIOA,4,1);
    af(GPIOA,5,0); af(GPIOA,6,0); af(GPIOA,7,0);
    af(GPIOA,8,0);
    RCC->CFGR |= RCC_CFGR_MCOSEL_0|RCC_CFGR_MCOSEL_1|RCC_CFGR_MCOPRE_0; /* HSI16/2 = 8 MHz. */
    af(GPIOA,9,1); af(GPIOA,10,1);
    RCC->APBENR1 |= RCC_APBENR1_TIM2EN;
    TIM2->PSC=15; TIM2->ARR=0xffffffff; TIM2->EGR=1; TIM2->CR1=1;
    RCC->APBENR2 |= RCC_APBENR2_SPI1EN|RCC_APBENR2_USART1EN;
    SPI1->CR1=SPI_CR1_MSTR|SPI_CR1_SSM|SPI_CR1_SSI|SPI_CR1_CPHA|SPI_CR1_BR_0; /* mode1, 4 MHz */
    SPI1->CR2=(7u<<SPI_CR2_DS_Pos)|SPI_CR2_FRXTH;
    SPI1->CR1 |= SPI_CR1_SPE;
    USART1->BRR=(16000000u+57600u)/115200u;
    USART1->CR1=USART_CR1_UE|USART_CR1_RE|USART_CR1_TE;
    SysTick_Config(16000);
    return true;
}
static bool transfer(const uint8_t tx[30], uint8_t rx[30])
{
    out(GPIOA,4,false);
    for(unsigned i=0;i<30;++i) {
        if(!wait_mask(&SPI1->SR,SPI_SR_TXE,true,10000)) goto fail;
        *(volatile uint8_t *)&SPI1->DR=tx[i];
        if(!wait_mask(&SPI1->SR,SPI_SR_RXNE,true,10000)) goto fail;
        rx[i]=*(volatile uint8_t *)&SPI1->DR;
    }
    if(!wait_mask(&SPI1->SR,SPI_SR_BSY,false,10000)) goto fail;
    out(GPIOA,4,true); return true;
fail: out(GPIOA,4,true); return false;
}
static void delay_us(uint32_t us) { uint32_t at=micros(); while((uint32_t)(micros()-at)<us) {} }
static bool register_write(uint8_t address,uint16_t data)
{
    uint8_t tx[30],rx[30]; ads_command((uint16_t)(0x6000u | ((uint16_t)address<<7)),data,tx);
    if(!transfer(tx,rx)) return false;
    ads_command(0,0,tx); if(!transfer(tx,rx)) return false;
    return ads_crc16(rx,27)==(uint16_t)((rx[27]<<8)|rx[28]) &&
        (uint16_t)((rx[0]<<8)|rx[1])==(uint16_t)(0x4000u|((uint16_t)address<<7));
}
static bool register_read(uint8_t address,uint16_t expected)
{
    uint8_t tx[30],rx[30]; ads_command((uint16_t)(0xa000u|((uint16_t)address<<7)),0,tx);
    if(!transfer(tx,rx)) return false;
    ads_command(0,0,tx); if(!transfer(tx,rx)) return false;
    return ads_crc16(rx,27)==(uint16_t)((rx[27]<<8)|rx[28]) &&
        (uint16_t)((rx[0]<<8)|rx[1])==expected;
}
static bool adc_init(void)
{
    out(GPIOA,1,false); delay_us(1000); out(GPIOA,1,true); delay_us(2000);
    uint8_t tx[30],rx[30]; ads_command(0,0,tx);
    if(!transfer(tx,rx) || (uint16_t)((rx[0]<<8)|rx[1])!=0xff28) return false;
    /* 24bit, RX CRC on, register CRC on, RESET cleared, timeout on. */
    if(!register_write(2,0x3110) || !register_write(3,0xff0e) ||
       !register_read(2,0x3110) || !register_read(3,0xff0e)) return false;
    /* Consume register-map change and sinc filter settling during inhibited startup. */
    delay_us(2000);
    /* TI SBAS950B 8.5.1.9: two immediate complete reads drain both FIFO
       slots after a pause. 2*60us < 256us conversion period. Ignore both;
       only subsequent DRDY edges may acquire timestamps/valid samples. */
    if(!transfer(tx,rx) || !transfer(tx,rx)) return false;
    adc=(ads_receiver_t){0}; drdy_pending=false; acquisition_overrun=false;
    EXTI->EXTICR[0] &= ~255u; EXTI->FTSR1 |= 1u; EXTI->RTSR1 &= ~1u;
    EXTI->FPR1=1; EXTI->IMR1 |= 1u;
    NVIC_SetPriority(EXTI0_1_IRQn,0); NVIC_EnableIRQ(EXTI0_1_IRQn);
    return true;
}
static bool ntc_init(void)
{
    RCC->APBENR2 |= RCC_APBENR2_ADCEN;
    ADC1->CR=ADC_CR_ADVREGEN; delay_us(100);
    ADC1->CFGR2=ADC_CFGR2_CKMODE_0; /* PCLK/2 = 8 MHz */
    ADC1->CFGR1=0; ADC1->SMPR=ADC_SMPR_SMP1; /* 160.5 cycles acquisition */
    ADC1->CR |= ADC_CR_ADCAL;
    if(!wait_mask(&ADC1->CR,ADC_CR_ADCAL,false,100000)) return false;
    delay_us(10); ADC1->ISR=ADC_ISR_ADRDY; ADC1->CR |= ADC_CR_ADEN;
    return wait_mask(&ADC1->ISR,ADC_ISR_ADRDY,true,100000);
}
static bool ntc_read(void)
{
    for(unsigned i=0;i<2;++i) {
        ADC1->CHSELR=1u<<(i+2); ADC1->ISR=ADC_ISR_EOC|ADC_ISR_EOS|ADC_ISR_OVR;
        ADC1->CR |= ADC_CR_ADSTART;
        if(!wait_mask(&ADC1->ISR,ADC_ISR_EOC,true,10000)) return false;
        ntc_raw[i]=(uint16_t)ADC1->DR;
        if(ADC1->ISR & ADC_ISR_OVR) return false;
    }
    ntc_sampled=milliseconds;
    return true; /* Raw acquisition success, not a temperature/coolness verdict. */
}
static void outputs(bool acquisition_health,bool heartbeat_ok)
{
    r5_supervisor_signals_t o=r5_supervisor_signals(&binding,acquisition_health,heartbeat_ok,
        post_record_fresh(&post,post.boot_nonce,milliseconds));
    out(GPIOB,14,o.run);out(GPIOC,15,o.admit);
    out(GPIOD,8,o.kpa);out(GPIOD,9,o.kpb);out(GPIOD,4,o.heartbeat_ok);
    out(GPIOC,4,o.k1);out(GPIOC,5,o.k2);
    /* Final proof edge has a full owner iteration of KT setup/hold. */
    out(GPIOB,13,o.bypass_proven);out(GPIOB,0,o.kb);out(GPIOB,1,o.kt);
    out(GPIOB,2,o.healthy);out(GPIOB,10,o.post_ok);out(GPIOB,11,o.reset_ok);
    out(GPIOB,12,o.precharge_done);out(GPIOB,15,o.stop_done);out(GPIOC,6,o.start_released);
}
static bool uart_poll
(void)
{
    if(USART1->ISR & (USART_ISR_ORE|USART_ISR_FE|USART_ISR_NE)) {
        USART1->ICR=USART_ICR_ORECF|USART_ICR_FECF|USART_ICR_NECF;
        uart_used=0; link.seen=false; return false;
    }
    if(uart_sent<uart_length && (USART1->ISR & USART_ISR_TXE_TXFNF))
        USART1->TDR=uart_tx[uart_sent++];
    if(uart_sent==uart_length && line_pending) {
        for(unsigned n=0;n<R5_LINE_BYTES;n++) uart_tx[n]=line_tx[n];
        uart_sent=0;uart_length=R5_LINE_BYTES;line_pending=false;
    }
    if(uart_sent==uart_length && (uint32_t)(milliseconds-uart_started)>=5) {
        energy_link_packet_t status={.kind=ENERGY_LINK_STATUS,.state=(uint8_t)supervisor.state,
          .sequence=++uart_sequence,.flags=(!supervisor.configured||supervisor.state==ENERGY_FAULT||binding.isolation.state==PC_FAULT)?ENERGY_LINK_FAULT:0};
        if(!energy_link_encode(&status,uart_tx)) return false;
        uart_sent=0;uart_length=ENERGY_LINK_SIZE;uart_started=milliseconds;
    }
    if(USART1->ISR & USART_ISR_RXNE_RXFNE) {
        uart_rx[uart_used++]=(uint8_t)USART1->RDR;
        if(uart_used==ENERGY_LINK_SIZE) {
            uart_used=0;
            if(!energy_link_receive(&link,ENERGY_LINK_COMMAND,uart_rx,20,milliseconds,&command)) {
                link.seen=false; return false;
            }
        }
    }
    return true;
}
/* No field calibration is invented. Commissioning is intentionally unavailable
   in this bench image. NTC, divider injection, proof-current/crest bounds and
   oscilloscope commissioning qualification must be supplied before an energized image exists. */
int main(void)
{
    if(!hardware_init()) r5_fault_shutdown();
    safe_outputs();
    energy_config_t cfg=energy_study_config();
    cfg.bus_max_v=230; cfg.catch_max_v=250; cfg.tank_max_v=1000;
    r5_supervisor_init(&binding,&cfg,0); /* commissioned remains false */
    bool init_ok=ntc_init() && adc_init();
    (void)r5_sensors_configure(&sensors); /* absent calibration fails closed */
    mirror_timer_init();
    uint32_t last_step=0,last_feed=0;
    ads_sample_t sample={0}; uint32_t sample_ms=0;
    for(;;) {
        uint32_t irq=__get_PRIMASK();__disable_irq();mirrors=mirror_scan;__set_PRIMASK(irq);
        bool serial_ok=uart_poll();
        if(drdy_pending) {
            __disable_irq(); uint32_t at=drdy_at, at_ms=drdy_ms; drdy_pending=false; __enable_irq();
            uint8_t tx[30],rx[30]; ads_command(0,0,tx);
            if(!transfer(tx,rx) || !ads_accept(&adc,rx,at,micros(),&sample)) adc.fault=true;
            else {
                sample_ms=at_ms;
                bool contacts=mirrors.qualified&&!mirrors.fault&&binding.out.k1&&
                    binding.out.k2&&!mirrors.raw[0]&&!mirrors.raw[1];
                (void)r5_sensors_sample(&sensors,&sample,binding.out.kt,contacts);
                if(sensors.measurement.complete && r5_line_encode(&sensors.measurement,line_tx))
                    line_pending=true;
            }
        }
        if(acquisition_overrun || !serial_ok) { safe_outputs(); post_record_consume(&post); }
        mirror_all_off=!binding.out.k1&&!binding.out.k2&&!binding.out.kb&&!binding.kpa&&!binding.kpb;
        mirror_discharged=sensors.valid&&sensors.physical[3]>=0&&sensors.physical[3]<30&&
            sensors.physical[4]>=0&&sensors.physical[4]<30;
        uint32_t now=milliseconds;

        uint32_t step_us=micros();
        if((uint32_t)(step_us-last_step)>=500) {
            last_step=step_us;
            if((uint32_t)(now-ntc_sampled)>=20) {
                ntc_ok=ntc_read();
                uint16_t codes[2]={ntc_raw[0],ntc_raw[1]};
                (void)r5_sensors_ntc(&sensors,codes);
            }
            energy_inputs_t in={0};
            in.now_ms=now; in.sampled_ms=sample_ms;
            in.start=pin(GPIOC,0); in.reset=pin(GPIOC,1); in.stop_ok=pin(GPIOC,2);
            in.hardware_ok=pin(GPIOB,9); in.hardware_latch_ok=pin(GPIOB,3);
            in.rails_ok=pin(GPIOC,11); in.bus_fault=pin(GPIOC,12);
            in.interlock_ok=pin(GPIOA,11);
            if(!in.rails_ok) heartbeat=(r5_heartbeat_t){0};
            bool heartbeat_ok=in.rails_ok&&r5_heartbeat_step(&heartbeat,pin(GPIOD,3),now);
            in.controller_alive=r5_controller_diagnostics(&link,&command,now,heartbeat_ok);
            in.heat_request=r5_controller_intent(&link,&command,now,heartbeat_ok,pin(GPIOC,10));
            in.pwm_qualified=in.controller_alive&&in.rails_ok&&in.interlock_ok; /* Commissioned on-chip contract, not external edge measurement. */
            /* Sensing and electrical contact qualification default false until
               analog calibration/POST/capture work is completed. Never infer a
               released contact from a passive mirror bit without excitation. */
            in.sensors_valid=sensors.valid&&ads_fresh(&adc,micros())&&
                r5_measurement_fresh(&sensors.measurement,micros())&&!mirrors.fault;
            in.receiver_ok=r5_mirror_fresh(&mirrors,micros());
            in.k1_released=mirrors.qualified&&mirrors.released[0];
            in.k2_released=mirrors.qualified&&mirrors.released[1];
            in.kb_released=mirrors.qualified&&mirrors.released[2];
            in.aux_ok=pin(GPIOB,9); /* BASIC_HEALTHY includes physical24Vwindow,PG5,WD/3V3;
                                    common gate path, not redundant independent rail sensing. */
            in.resistor_cool=sensors.cold;
            in.manual_post_ok=post_record_fresh(&post,post.boot_nonce,now);
            in.manual_post_serial=post.serial;
            in.bus_v=(float)sensors.physical[3];in.catch_v=(float)sensors.physical[4];
            in.tank_abs_v=(float)(sensors.physical[5]<0?-sensors.physical[5]:sensors.physical[5]);
            in.line_rms_v=(float)sensors.measurement.rms[0];in.inlet_rms_a=(float)sensors.measurement.rms[7];
            in.valid_line_cycles=(uint8_t)(sensors.measurement.serial>255?255:sensors.measurement.serial);
            in.precharge_complete=sensors.measurement.precharge_ok;
            in.proof_current_valid=sensors.measurement.proof_ok;
            if(!binding.out.kb||mirrors.raw[2]||mirrors.fault) bypass_proven=false;
            else if(r5_bypass_loaded(&sensors.measurement)) bypass_proven=true;
            in.bypass_closed_electrically=bypass_proven;
            in.catch_charge_proven=sensors.measurement.catch_ok;
            r5_supervisor_inputs_t joined={.energy=in,.now_us=step_us,
                .mirror_us=mirrors.published_us,.measurement_serial=sensors.measurement.serial,
                .mirror_valid=in.receiver_ok,.feedback_static=mirrors.static_ready,
                .kpa_nc=mirrors.raw[3],.kpb_nc=mirrors.raw[4],
                .loaded_bypass_proof=r5_bypass_loaded(&sensors.measurement),.proof_window_high=pin(GPIOB,8),
                .hardware_attempt=pin(GPIOB,4),.hardware_total_window=pin(GPIOB,6)};
            r5_supervisor_step(&binding,&joined);
            if(binding.consume_post) post_record_consume(&post);

            outputs(init_ok && ntc_ok && !acquisition_overrun && ads_fresh(&adc,micros()),
                    in.controller_alive);
        }
        if(init_ok && !acquisition_overrun && ads_fresh(&adc,micros()) && (uint32_t)(now-last_feed)>=20) {
            out(GPIOC,3,!pin(GPIOC,3)); last_feed=now;
        }
        /* Busy-poll UART while waiting for DRDY: WFI could sleep across RX bytes. */
    }
}
