# EXP-10: Balance SPI Escape Layers

## Summary
Moved SPI_CLK and SPI_CS_TEMP escape routes from In1.Cu to In2.Cu to reduce
congestion on In1.Cu layer where USB and high-data-rate SPI signals compete.

## Results

| Metric | EXP-9 Baseline | After EXP-10 | Change |
|--------|----------------|--------------|--------|
| Total violations | 99 | 91 | -8 (-8.1%) |
| SPI total | 36 | 28 | -8 (-22%) |
| SPI_MISO+MOSI | 24 | 16 | -8 (-33%) |

### Per-net breakdown:

| Net | EXP-9 | EXP-10 | Change |
|-----|-------|--------|--------|
| SPI_MOSI | 11 | 5 | -6 (-55%) |
| SPI_MISO | 13 | 11 | -2 (-15%) |
| SPI_CLK | 8 | 8 | 0 |
| SPI_CS_TEMP | 4 | 4 | 0 |

## Analysis

Moving SPI_CLK and SPI_CS_TEMP to In2.Cu freed up routing channels on In1.Cu.
The primary beneficiary was SPI_MOSI which dropped from 11 to 5 violations.

The SPI_CLK and SPI_CS_TEMP themselves didn't change (8 and 4) because they
now compete with GATE_* and PWM_* on In2.Cu, but this tradeoff benefits the
higher-violation SPI_MOSI and SPI_MISO nets.

## Cumulative Progress

| Experiment | Total Violations | Change |
|------------|-----------------|--------|
| Baseline | 102 | - |
| EXP-8 (Power planes) | 102 | 0% |
| EXP-9 (Analog B.Cu) | 99 | -3% |
| EXP-10 (SPI balance) | 91 | -11% |

Total improvement: 102 → 91 = **-11 violations (-10.8%)**
