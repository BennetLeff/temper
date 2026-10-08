# Catch fuse-holder selection

**Candidate for detailed layout: Mersen US141, item Z331153, one pole, without
indicator.** It takes the energy packet's 14 × 51 mm Eaton FWP-10A14F candidate.
This fixes the holder identity for a mechanical/coordination evaluation; it
does not approve a cross-manufacturer fuse/holder combination or prove fit.

The [manufacturer's exact part page](https://www.mersen.com/en/products/ultrasafe-us14-modular-fuse-holders/z331153-us141)
identifies 14 × 51 mm and 1000 V DC UL rating. The
[US14 datasheet, DS-PACYUS14-11-1220_EN](https://www.mersen.com/sites/default/files/medias/PIM/files/DS-Semiconductor-Modular-Fuse-Holders-UltraSafe-US14-EN.pdf),
pp. 1–3, lists a 750 V DC overview rating, 50 A thermal current with derating,
−25…60°C operation, and DC20B non-load use. A holder is not a load-breaking
disconnect; isolate and verify discharged bus **and catch** before opening it.
Do not import its component IP20 claim into a completed enclosure claim.

The packaging owner visually checked the primary drawing on p. 4: US141 is
26.5 mm wide × 107 mm high × 76.5 mm closed depth, with 94 mm opening projection.
It **cannot fit orthogonally inside the 80 × 60 × 60 mm catch reservation**:
its 107 mm dimension exceeds the longest available side. This is a concrete
dimensional blocker, not simply missing measurement. Reallocate the catch
carrier or a separate nearby holder bay, including mounting, service sweep,
terminals and wire bends. The capacitor, diode, fuse, bleeds, sensing and busbar
carrier must be packaged together before a complete fit claim. Keep the fuse on the
bus side of the catch diode, within the evaluated hazardous-energy enclosure;
never extend its unprotected lead to the external inlet pod merely to obtain room.

The [subsequent wider carrier](../packaging/catch-alternative.md) gives a concrete
alternative: rotate the holder's 107 mm axis across the cooker, place the
capacitor above it and move the rear mains-wire corridor. The final nominal
body, cover, opening-projection and channel intersection sets are empty. This
resolves the rectangular body-space conflict only. Supplier mounting-orientation
approval, actual DIN support, lead/boot envelopes, service access and insulation
remain open. In particular, the revised bleed/sense-card allocation is only
36 × 20 × 10 mm; no complete eight-resistor/isolated-monitor layout has been
shown to fit it.

Before adoption, reconcile the selected fuse's power dissipation and DC clearing
conditions with the holder's allowed fuse loss, contact temperature, conductor
class and installation orientation. The holder's voltage/current number does
not establish semiconductor-fuse coordination or capacitor-short containment.
