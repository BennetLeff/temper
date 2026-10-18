# temper-mining-r3

2026-10-15. Round 3 is decision-grade input on what temper should do. It
covers:

- the three videos that were rate-limited in round 2, transcribed locally;
- the primary regulatory texts: UL 858 induction and smart-enabled clauses,
  47 CFR 18.301/305/307, and 10 CFR 430.2/430.32;
- sensorless pan-temperature literature and patents;
- the competitor and market picture.

| File | What it is |
|---|---|
| `FINDINGS.md` | Evidence ledger, tagged said / yt / doc / reg / patent / web / model / inferred |
| `RECOMMENDATIONS.md` | Ranked actions with owner, confidence and effort, plus where they contradict current temper decisions |
| `boil_time.py` → `boil-time.json` | Temper input-power options against the Control Freak's measured 2 L boil (10:55) |
| `burst_ripple.py` → `burst-ripple.json` | Pan ripple under temper's line-synchronous burst mode. Imports the sensor-r2 pan model read-only. |
| `impedance_sensitivity.py` → `impedance-sensitivity.json` | How finely the reflected resistance can resolve pan temperature (an upper-bound estimate) |

Run each with `python3 <script>`.

Media and source texts live outside the repo:

- transcripts: `~/temper-media/{7TZb8I5rVZ8,G-GHxlLsCy8,ctVXMv_4Glw}/captions.txt`
- regulatory texts: `~/temper-media/regulatory/`
- patents: `~/temper-media/mining-r3/patents/`
- Control Freak quick start: `~/temper-media/control-freak-docs/`

New tool: `scripts/video_mining/audio_transcript.sh`. It downloads the audio
only and runs Whisper locally, as a fallback when YouTube's subtitle endpoint
returns HTTP 429.

## Primary sources

- **Regulations:**
  - [47 CFR 18.305](https://www.law.cornell.edu/cfr/text/47/18.305)
  - [47 CFR 18.307](https://www.law.cornell.edu/cfr/text/47/18.307)
  - [10 CFR 430.32](https://www.law.cornell.edu/cfr/text/10/430.32)
  - [10 CFR 430.2](https://www.law.cornell.edu/cfr/text/10/430.2)
  - [UL 858 SUN (Intertek)](https://cdn.intertek.com/www-intertek-com/dms-legacy/UL-858-Rev-2-8-2017-and-11-1-2017-ED-9-1-2020.pdf)
  - [ECM Code Q&A on cord-and-plug loads](https://www.ecmweb.com/qampa/code-qa-13)
- **Patents:**
  - [US10085303B2](https://patents.google.com/patent/US10085303B2/en)
  - [US8530805B2](https://patents.google.com/patent/US8530805B2/en)
- **Breville:**
  - [Breville BMC800](https://www.breville.com/en-us/product/bmc800)
  - [CMC850 quick start](https://assets.breville.com/CMC850/CMC850BSS_USC_QS_SA_A22_LR.pdf)
- **Reviews and forums:**
  - [Rational Kitchen review](https://therationalkitchen.com/breville-control-freak-home-induction-cooktop-review/)
  - [Hungry Onion thread](https://www.hungryonion.org/t/control-freak/30448?page=5)
  - [Digital Trends Hestan Cue](https://www.digitaltrends.com/appliance-reviews/hestan-cue-review/)
- **Market:**
  - [Copper Charlie (Domino)](https://www.domino.com/design-by-room/copper-charlie-range-review/)
  - [Impulse/BS Service Eximius](https://aijourn.com/impulse-labs-brings-high-performance-induction-cooking-to-europe-with-new-eximius-cooktop/)
  - [Stanford Magazine on Impulse](https://stanfordmag.org/contents/hot-stuff)
- **Papers:**
  - [Sensors 14:5278 (IR)](https://dx.doi.org/10.3390/s140305278)
  - [KIEE 71(9):1230](https://scholarworks.unist.ac.kr/handle/201301/60061)
  - [Energies 15:1294](https://ideas.repec.org/a/gam/jeners/v15y2022i4p1294-d746442.html)
- **Videos:**
  - yt:7TZb8I5rVZ8 (Cars & Capitalists, Impulse CEO, 2026-10-08)
  - yt:G-GHxlLsCy8 (Kaizer Power Electronics, SMEG 10 kW)
  - yt:ctVXMv_4Glw (Tech Dregs, Amazon Basics)
  - yt:BcSqJ7sZiAQ (Eater, Control Freak)
