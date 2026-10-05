/* STM32G071RBT6 round4 supervisor pin contract. CMSIS device header from ST. */
#include "stm32g071xx.h"
#include "acquisition.h"
#include "energy_supervisor.h"
#include "energy_link.h"
#include <stdbool.h>
#include <stdint.h>
uint32_t SystemCoreClock = 16000000;
static volatile uint32_t drdy_at,drdy_ms;
static volatile bool drdy_pending, acquisition_overrun;
static volatile uint32_t milliseconds;
static uint8_t uart_rx[ENERGY_LINK_SIZE];
static unsigned uart_used;
static uint8_t uart_tx[ENERGY_LINK_SIZE];
static unsigned uart_sent=ENERGY_LINK_SIZE;
static uint32_t uart_sequence, uart_started;
static volatile uint16_t ntc_raw[2];
static bool ntc_ok;
static uint32_t ntc_sampled;
static energy_link_receiver_t link;
static energy_link_packet_t command;
static ads_receiver_t adc;
static energy_supervisor_t supervisor;
static post_record_t post;
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
    GPIOC->BSRR = ((1u<<4)|(1u<<5)|(1u<<6)) << 16;
    GPIOB->BSRR = ((1u<<0)|(1u<<1)|(1u<<2)|(1u<<10)|(1u<<11)|(1u<<12)|(1u<<13)) << 16;
    out(GPIOB,15,true);
}
void r5_fault_shutdown(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOBEN|RCC_IOPENR_GPIOCEN;
    (void)RCC->IOPENR;
    safe_outputs();
    /* Stop feeding WDI. Independent hardware timeout/reset remains active. */
    for(;;) {}
}
static bool wait_mask(volatile uint32_t *reg, uint32_t mask, bool set, uint32_t bound)
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
    const unsigned a_inputs[]={0,11};
    for(unsigned i=0;i<2;++i) mode(GPIOA,a_inputs[i],0);
    for(unsigned i=3;i<=9;++i) mode(GPIOB,i,0);
    const unsigned c_inputs[]={0,1,2,7,8,9,10,11,12};
    for(unsigned i=0;i<sizeof c_inputs/sizeof c_inputs[0];++i) mode(GPIOC,c_inputs[i],0);
    for(unsigned i=3;i<=6;++i) mode(GPIOD,i,0);
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
    delay_us(2000); if(!transfer(tx,rx)) return false;
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
static void outputs(const energy_supervisor_t *s, bool independent_health)
{
    if(!s->configured || !independent_health || s->state==ENERGY_FAULT) {
        safe_outputs(); return;
    }
    out(GPIOB,14,s->out.sup_run_ok);
    out(GPIOC,4,s->out.k1); out(GPIOC,5,s->out.k2);
    out(GPIOB,0,s->out.kb); out(GPIOB,1,s->out.kt);
    out(GPIOB,2,independent_health);
    out(GPIOB,10,post_record_fresh(&post,post.boot_nonce,milliseconds));
    out(GPIOB,11,s->out.reset_ok);
    out(GPIOB,12,s->state>=ENERGY_BYPASS_CLOSE && s->state<=ENERGY_RUN);
    out(GPIOB,13,s->state>=ENERGY_RAIL_QUALIFY && s->state<=ENERGY_RUN);
    out(GPIOB,15,s->state==ENERGY_OFF || s->state==ENERGY_DISCHARGE);
    out(GPIOC,6,s->start_released && post.valid);
}
static bool uart_poll(void)
{
    if(USART1->ISR & (USART_ISR_ORE|USART_ISR_FE|USART_ISR_NE)) {
        USART1->ICR=USART_ICR_ORECF|USART_ICR_FECF|USART_ICR_NECF;
        uart_used=0; link.seen=false; return false;
    }
    if(uart_sent<ENERGY_LINK_SIZE && (USART1->ISR & USART_ISR_TXE_TXFNF))
        USART1->TDR=uart_tx[uart_sent++];
    if(uart_sent==ENERGY_LINK_SIZE && (uint32_t)(milliseconds-uart_started)>=5) {
        energy_link_packet_t status={.kind=ENERGY_LINK_STATUS,.state=(uint8_t)supervisor.state,
          .sequence=++uart_sequence,.flags=ENERGY_LINK_FAULT};
        if(!energy_link_encode(&status,uart_tx)) return false;
        uart_sent=0; uart_started=milliseconds;
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
   fast-capture qualification must be supplied before an energized image exists. */
int main(void)
{
    if(!hardware_init()) r5_fault_shutdown();
    safe_outputs();
    energy_config_t cfg=energy_study_config();
    cfg.bus_max_v=230; cfg.catch_max_v=250; cfg.tank_max_v=1000;
    energy_supervisor_init(&supervisor,&cfg,0); /* commissioned remains false */
    bool init_ok=ntc_init() && adc_init();
    uint32_t last_step=0,last_feed=0;
    ads_sample_t sample={0}; uint32_t sample_ms=0;
    for(;;) {
        bool serial_ok=uart_poll();
        if(drdy_pending) {
            __disable_irq(); uint32_t at=drdy_at, at_ms=drdy_ms; drdy_pending=false; __enable_irq();
            uint8_t tx[30],rx[30]; ads_command(0,0,tx);
            if(!transfer(tx,rx) || !ads_accept(&adc,rx,at,micros(),&sample)) adc.fault=true;
            else sample_ms=at_ms;
        }
        if(acquisition_overrun || !serial_ok) { safe_outputs(); post_record_consume(&post); }
        uint32_t now=milliseconds;
        if(now!=last_step) {
            last_step=now;
            if((uint32_t)(now-ntc_sampled)>=20) ntc_ok=ntc_read();
            energy_inputs_t in={0};
            in.now_ms=now; in.sampled_ms=sample_ms;
            in.start=pin(GPIOC,0); in.reset=pin(GPIOC,1); in.stop_ok=pin(GPIOC,2);
            in.hardware_ok=pin(GPIOB,9); in.hardware_latch_ok=pin(GPIOB,3);
            in.rails_ok=pin(GPIOC,11); in.bus_fault=pin(GPIOC,12);
            in.interlock_ok=pin(GPIOA,11);
            in.controller_alive=energy_link_fresh(&link,now)&&pin(GPIOD,4);
            /* Sensing and electrical contact qualification default false until
               analog calibration/POST/capture work is completed. Never infer a
               released contact from a passive mirror bit without excitation. */
            in.sensors_valid=false; in.aux_ok=false;
            energy_supervisor_step(&supervisor,&in);
            outputs(&supervisor,init_ok && ntc_ok && !acquisition_overrun && ads_fresh(&adc,micros()));
        }
        if(init_ok && !acquisition_overrun && ads_fresh(&adc,micros()) && (uint32_t)(now-last_feed)>=20) {
            out(GPIOC,3,!pin(GPIOC,3)); last_feed=now;
        }
        /* Busy-poll UART while waiting for DRDY: WFI could sleep across RX bytes. */
    }
}
