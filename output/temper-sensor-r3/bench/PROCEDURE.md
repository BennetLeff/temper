# Cookware contact survey: procedure

**Goal:** decide whether C1 stands. Every pan must give a C1-equivalent dry
τ63 of **≤ 1.2 s**, the bar in `../DECISIONS.md` §5. **Any pan above
1.35 s means stop** and go back through the §5 escalation.

The method is the one §5 sets: a pan preheated off-hob, set on a cold
sensor, coil off. Rig and logger are in `RIG.md`; analysis is `fit.py`.

## 1. Cookware set

Use **at least 12 pans covering all six classes** in
`../contact_model.py`; `fit.py survey` reports coverage. Aim for the 15
below. Record every pan on `datasheet_template.csv` before testing.

| # | Pan | contact_model class | Why it's in |
|---|---|---|---|
| 1 | Tri-ply clad skillet, polished stainless base | clad_polished_ss | The smooth extreme |
| 2 | 5-ply clad saucepan | clad_polished_ss | Second clad sample, different maker |
| 3 | Disc-base stockpot, brushed stainless | disc_base_brushed | Encapsulated aluminium disc |
| 4 | Aluminium non-stick pan with a stainless induction plate (perforated insert) | disc_base_brushed | **Aluminium-disc base.** Mixed surface: insert ridges and aluminium |
| 5 | Thin stainless pan with a visibly concave base (budget brand) | disc_base_brushed | **Warped:** concave centre, the classic Control Freak failure |
| 6 | Carbon-steel skillet (de Buyer / Matfer class) | carbon_steel | Thin, may warp |
| 7 | Flat-bottom carbon-steel wok | carbon_steel | Small flat, large overhang |
| 8 | Machined or smooth cast iron (Field / Smithey class) | cast_iron_machined | |
| 9 | As-cast cast iron (Lodge class) | cast_iron_as_cast | **Rough:** C1's modelled worst (h 888) |
| 10 | Old, heavily seasoned as-cast pan or griddle | cast_iron_as_cast | **Rough plus seasoning build-up** |
| 11 | Enamelled cast iron (Le Creuset / Staub class) | enamel_cast_iron | **Enamelled**, hard face |
| 12 | Enamelled steel pot | enamel_cast_iron | Thin enamel on steel |
| 13 | Small pan, base Ø ≤ 14 cm (butter warmer or milk pan) | its own class | **Small:** light pan, low weight on the disc |
| 14 | Pan with a domed base (convex centre) | its own class | **Warped**, the opposite sign to #5 |
| 15 | Well-used, scratched stainless pan | clad or disc | **Rough** stainless |

For each pan, record:
- **base flatness:** a straightedge across the centre, with feeler gauges or
  the dial indicator. + is concave, the centre lifted off the plate;
  − is convex;
- **Ra class** from the comparator plate;
- **whether it rocks** on the plate.

## 2. Conditions and repeats

| Condition (`logger.py --condition`) | Proud | Tip force | Pan temperature | Pans | Repeats | Gated |
|---|---|---|---|---|---|---|
| `dry_nominal` | 0.60 mm | 1.5 N | 150 °C | all | 5 | **yes** |
| `dry_force_low` / `dry_force_high` | 0.60 | 1.2 / 1.8 N | 150 | #1, #5, #9, #11, #13 | 3 each | no (sensitivity) |
| `dry_proud_0p5` / `dry_proud_0p7` | 0.50 / 0.70 | 1.5 | 150 | #5, #9, #14 | 3 each | no |
| `hot_230` | 0.60 | 1.5 | 230 °C | #6, #9, #11 | 3 | no; warp and air-k check |
| `oiled` | 0.60 | 1.5 | 150 | #1, #9 | 3 | no; a thin wipe of oil on the base |
| `paste_cal` | — | — | 150 °C copper block | probe | 3 | sets `tau_int_s` |

The 150 °C standard matches the air temperature the contact model uses (k_air
at 150 °C). Only `dry_nominal` is gated; the other conditions show where
the margin goes.

## 3. Paste calibration (each probe, before the survey and after it)

1. Heat the copper block to 150 °C on a hot plate. Put the type-K bead in a
   Ø1 hole in the block.
2. Put a thin film of Wakefield 120 on the disc. Press the block down
   squarely onto it.
3. Log 10 s: `python logger.py --port … --pan cu_block --condition paste_cal --repeat N`.
4. Run `python fit.py calibrate runs/cu_block__paste_cal__rN.csv`, which
   writes `tau_int_s` into `probe.json`.
5. **Pass:** the 3 repeats agree within ±0.015 s, the band `fit.py` assumes.
   Clean the paste off with IPA before any dry run.

## 4. One set-down

1. **Heat:** pan in the oven at the condition temperature for ≥ 20 min
   (cast iron ≥ 30 min). The reference TC must read within 5 K of target.
2. **Probe start:** within 2 K of ambient (`logger.py` shows it). Blow air
   over it between runs if needed.
3. Start `logger.py` with 20 s and the pan, class, condition and repeat.
4. **Set down within 5 s:**
   - centre the pan over the probe, within 10 mm, using the scribed rings
     on the plate;
   - lower it vertically and release it from ≤ 5 mm;
   - press BOOT as you let go;
   - don't touch the pan again.
5. Leave it for the rest of the 20 s. Lift it straight off. The pan goes back
   in the oven for ≥ 5 min before the next repeat.
6. Run `python fit.py run runs/<file>.csv` straight away. **Reject and
   repeat** if any of these hold:
   - fit rms > 0.3 K;
   - the pan was nudged;
   - `logger.py` reported a fault or a rate below 20 Hz.

## 5. Analysis and decision

Run `python fit.py survey runs/`, which writes `runs/survey-results.json`.

Each pan is judged on its **worst `dry_nominal` repeat**, using the fitted
C1 τ63 and its systematic band:

| Verdict | Condition |
|---|---|
| PASS | τ63 + band ≤ 1.2 s |
| STOP | τ63 − band > 1.35 s |
| MARGINAL | anything in between |

**Overall:**
- **PASS:** every gated pan passes and coverage is complete. C1 stands.
- **MARGINAL:** run the force and proud sensitivity on that pan and reduce
  the band (weigh the elements). Decide from the improved number.
- **STOP:** go back through `../DECISIONS.md` §5 steps 1–3: face finish and
  tilt, a thinner disc, then active measurement after FTO.

Archive `runs/`, `probe.json`, the data sheets and photos of every pan base.

## 6. Safety

- Pans at 150–230 °C: wear rated gloves and use a stable bench. Keep a
  trivet by the oven; never set a hot pan on the plate's edge or the logger.
- **Oil runs:** use only a thin film, not a pool, at 150 °C, well below the
  smoke point. Keep a lid and a class K/B extinguisher at hand, and never use
  water on hot oil.
- At 230 °C, seasoning on cast iron smokes. Ventilate.
- The glass-ceramic plate takes the heat. Calcium-silicate board must not
  get wet.
- Both the probe disc and the bore edge are brittle. Don't slide pans across
  the probe; lift them off.
