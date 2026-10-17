# AOE-26 discharge times; also AOE-24 barrier margin and AOE-07 resistor voltages
import math
tau=200e3*2.4e-6; print("X-cap 198->34 V: %.3f s (limit 1 s)"%(tau*math.log(198/34)))
Rb=1/(1/440e3+1/1895.8e3)
for C in (18.8e-6,20.68e-6): print("DC link C=%.1fuF 280->60 V: %.1f s"%(C*1e6,Rb*C*math.log(280/60)))
print("bank 484->60 V: %.2f s"%(1.88e6*0.5e-6*math.log(484/60)))
print("D5 margin 8.047-8.0 = %.3f mm"%(8.047-8.0))
print("OVP-corner volts: bleed 220k each %.0f V, divider 470k each (4 in string) %.0f V"%(280/2,280/4))
