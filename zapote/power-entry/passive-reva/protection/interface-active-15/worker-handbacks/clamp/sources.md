# Primary sources used

* Analog Devices, **LT4363 Rev C**, `https://www.analog.com/media/en/technical-documentation/data-sheets/4363fb.pdf`.
  Pinout and electrical limits: pp. 1--3; timer and operation: pp. 7--11;
  MOSFET SOA, P2t and gate network: pp. 12--15.
* Infineon/International Rectifier, **IRLR2908PbF**,
  `https://www.infineon.com/assets/row/public/documents/24/49/infineon-irlr2908-datasheet-en.pdf`.
  Ratings and SOA plot: pp. 1--4.

The 35 V input is inherited as an explicit engineering assumption from
interface-physical-14; it is not a guaranteed Mean Well IRM-10-24 transient
specification. The candidate therefore remains conditional until that source
waveform and impedance are measured or bounded.
