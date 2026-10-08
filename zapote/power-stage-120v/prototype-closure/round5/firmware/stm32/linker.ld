ENTRY(Reset_Handler)
MEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 128K
         RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 36K }
_estack = ORIGIN(RAM)+LENGTH(RAM);
SECTIONS {
 .isr_vector : { KEEP(*(.isr_vector)) } > FLASH
 .text : { *(.text*) *(.rodata*) } > FLASH
 .ARM.exidx : { *(.ARM.exidx*) } > FLASH
 _sidata = LOADADDR(.data);
 .data : { _sdata = .; *(.data*) _edata = .; } > RAM AT > FLASH
 .bss (NOLOAD) : { _sbss = .; *(.bss*) *(COMMON) _ebss = .; } > RAM
 . = ALIGN(8); _end = .;
 ASSERT(_end < _estack-2048, "Require 2 KiB minimum stack")
}
