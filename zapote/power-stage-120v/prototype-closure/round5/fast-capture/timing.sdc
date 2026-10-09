# Candidate 80 MHz clock constraints. No PLL or generated clocks.
create_clock -name capture80 -period 12.5 [get_ports clk80]
# Deliberately do NOT globally false-path the asynchronous input ports.
# Tool-specific paths to first-stage synchronizers must be inspected and
# exceptions narrowly applied; sync1->sync2 and SPI sync stages remain timed.
# SPI has 200 ns CS setup, >=50 ns SCLK high/low, >=2 us CS idle, dedicated bus.
# Post-route external I/O delay budget and metastability MTBF remain unverified.
