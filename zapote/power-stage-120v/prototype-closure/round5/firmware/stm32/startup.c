#include <stdint.h>
extern uint32_t _estack,_sidata,_sdata,_edata,_sbss,_ebss;
extern int main(void);
extern void SystemInit(void),SysTick_Handler(void),EXTI0_1_IRQHandler(void);
extern void r5_fault_shutdown(void);
void Default_Handler(void) { r5_fault_shutdown(); }
void Reset_Handler(void)
{
    uint32_t *src=&_sidata;
    for(uint32_t *dst=&_sdata;dst<&_edata;) *dst++=*src++;
    for(uint32_t *dst=&_sbss;dst<&_ebss;) *dst++=0;
    SystemInit(); (void)main(); Default_Handler();
}
__attribute__((section(".isr_vector"),used))
void (*const vectors[48])(void)={
    [0]=(void (*)(void))&_estack,[1]=Reset_Handler,[2]=Default_Handler,[3]=Default_Handler,
    [11]=Default_Handler,[14]=Default_Handler,[15]=SysTick_Handler,
    [16 ... 47]=Default_Handler,[21]=EXTI0_1_IRQHandler
};
