* BAV23C-E3-08, selected die (Vishay common-cathode SOT-23).
* No official Vishay SPICE deck was found in the 3-minute source check;
* this is an explicitly typical/assumed silicon model for topology tests only.
* Source-bound facts: Vishay BAV23C datasheet, 86374, downloaded 2026-09-19:
* https://www.vishay.com/docs/86374/bav23c.pdf
* Datasheet facts are not model guarantees: VRRM=250 V min, VF max 1.0 V
* at IF=100 mA / 25 C, VF max 1.25 V at IF=200 mA / 25 C, TJ=-55..150 C.
.model BAV23C_TYP D(Is=1e-12 N=1.5 Rs=2 Cjo=2p M=0.33 Vj=0.75 Tt=50n Bv=250 Ibv=100u)
