# Current-sense clamp disposition

Luna's read-only review found no new primary-source guarantee that closes the
current clamp selection. The parent checked the cited datasheets and retains
**BAV23C-E3-08 as a provisional candidate**, with no component deletion or swap.

TI's UCC28180 ISENSE guidance calls for a clamp that preserves the peak-current
threshold while limiting the negative pin excursion. Its stated forward-voltage
window is between the 0.438 V maximum PCL magnitude and 1.1 V across temperature
and variation. The ±1 mA pin-current stress rating is not an allowable sensing
error. [TI UCC28180 Rev D, §8.3.14](https://www.ti.com/lit/ds/symlink/ucc28180.pdf).

Vishay's BAV23C electrical table specifies forward-voltage maxima at 100 and
200 mA at 25 °C. Those points do not establish the required low-current,
temperature and production envelope for this assembled clamp.
[Vishay BAV23C](https://www.vishay.com/docs/86374/bav23c.pdf).

The engineering question has two parts: bound diode loading around normal/PCL
sense voltages, and bound the negative pin voltage during the actual fault
current. A single nominal forward-voltage number does not answer both.
Neither the shunt-fault waveform nor the permissible clamp-induced sensing
error has been sufficiently bounded. Keep the post-220 Ω diode location,
correct polarity and 1 nF filter explicit in any further evaluation.

The BAT54H option already examined in revision 09 is not promoted as a
replacement. The earlier assumed BAV23C model's hot failures are also not
measured BAV23C failures. Its 1 µA/2 mV limits were project screens, not vendor
acceptance criteria. Repeating that nominal model cannot produce the missing
guarantees.

Existing application-data drafts in revision 09's `manufacturer-questions.md`
already request the missing low-current/temperature bounds, controller sensing
error guidance and pulse conditions. No vendor was contacted in this round.
If application guarantees remain unavailable, physical characterization or an
alternative qualified topology is required before hardware acceptance.

Other Block B work remains: bind shunt/current/frequency tolerances, feedback
and compensation to the actual plant, then resolve magnetic and semiconductor
loss/thermal assumptions. Fuse interruption, bank observation and stored-energy
paths cannot be removed by treating controller current limiting as equivalent.
