import re,sys,collections
txt=open(sys.argv[1]).read().split('\n')
start=next(i for i,l in enumerate(txt) if l.startswith('Linker script and memory map'))
sizes=collections.Counter(); pend=None
rx=re.compile(r'^\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.a)\((\S+\.obj)\)\s*$')
rx2=re.compile(r'^\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S+\.obj)\s*$')
for l in txt[start:]:
    m=rx.match(l)
    if m and int(m.group(2),16): sizes[(m.group(3).split('/')[-1],m.group(4))]+=int(m.group(2),16)
for (a,o),s in sorted(sizes.items()):
    if a in('libmain.a','libtemper_hal.a','libpower.a') and (o.startswith(('main','state_','thermal_io','hal_','controller_board_esp32','n21_hw_esp32'))):
        print(f"{a}({o})  {s} bytes")
