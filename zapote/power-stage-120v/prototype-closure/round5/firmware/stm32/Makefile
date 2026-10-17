# Supply official ST device + ARM CMSIS Core include directories; no mock headers.
ROOT := ../../../../../..
CC := arm-none-eabi-gcc
OUT ?= $(ROOT)/output/temper-prototype-closure/round5/firmware
CFLAGS := -std=gnu11 -mcpu=cortex-m0plus -mthumb -Os -ffunction-sections -fdata-sections -Wall -Wextra -Werror -Wno-override-init -DSTM32G071xx -I$(CMSIS_DEVICE) -I$(CMSIS_CORE) -I../common -I$(ROOT)/firmware/components/power/include
SOURCES := platform.c startup.c ../common/acquisition.c $(ROOT)/firmware/components/power/energy_supervisor.c $(ROOT)/firmware/components/power/energy_link.c
all: $(OUT)/supervisor-bench.elf
$(OUT)/supervisor-bench.elf: $(SOURCES) linker.ld
	mkdir -p $(OUT)
	$(CC) $(CFLAGS) $(SOURCES) -nostartfiles -Tlinker.ld --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections -Wl,-Map=$(OUT)/supervisor-bench.map -lm -o $@
clean:
	rm -f $(OUT)/supervisor-bench.elf $(OUT)/supervisor-bench.map
