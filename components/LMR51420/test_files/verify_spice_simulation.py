#!/usr/bin/env python3
"""
LMR51430 SPICE Simulation Verification Tool

This script analyzes ngspice simulation results to verify the LMR51430
behavioral model is working correctly for induction cooker applications.

Usage:
    python3 verify_spice_simulation.py <raw_file>

Requirements:
    pip3 install numpy matplotlib PyLTSpice

Author: Generated for LMR51430 induction cooker power supply design
Date: 2025-12-09
"""

import sys
import os
import argparse
import numpy as np
from pathlib import Path

# Try to import PyLTSpice for reading raw files
try:
    from PyLTSpice import RawRead
    HAS_PYLTSPICE = True
except ImportError:
    HAS_PYLTSPICE = False
    print("WARNING: PyLTSpice not installed. Install with: pip3 install PyLTSpice")

# Try to import matplotlib for plotting
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("WARNING: matplotlib not installed. Plotting disabled.")

class LMR51430Validator:
    """
    Validates SPICE simulation results for LMR51430 buck converter
    """

    def __init__(self, specs=None):
        """Initialize with expected specifications"""
        if specs is None:
            # Default specs for 12V->5V @ 3A induction cooker application
            self.specs = {
                'VIN_NOM': 12.0,
                'VOUT_TARGET': 5.0,
                'IOUT_TARGET': 2.0,  # 2A load in test circuit
                'FSW_NOM': 500e3,  # 500kHz
                'VOUT_TOL': 0.075,  # ±7.5% (1.5% target + margin)
                'VOUT_RIPPLE_MAX': 0.100,  # 100mV p-p max
                'EFFICIENCY_MIN': 0.85,  # 85% minimum
                'STARTUP_TIME_MAX': 0.010,  # 10ms max startup
                'SOFT_START_TIME': 0.004,  # 4ms typ
            }
        else:
            self.specs = specs

        self.results = {}
        self.raw_data = None

    def parse_ascii_raw(self, filename):
        """
        Parse ngspice ASCII raw file manually if PyLTSpice not available
        """
        print(f"Parsing ASCII raw file: {filename}")

        data = {}
        variables = []

        try:
            with open(filename, 'r') as f:
                lines = f.readlines()

            # Find header section
            in_header = True
            num_points = 0
            num_vars = 0

            for i, line in enumerate(lines):
                if 'No. of Variables:' in line:
                    num_vars = int(line.split(':')[1].strip())
                elif 'No. of Points:' in line:
                    num_points = int(line.split(':')[1].strip())
                elif 'Variables:' in line:
                    # Parse variable names
                    var_idx = i + 1
                    for j in range(num_vars):
                        var_line = lines[var_idx + j].strip()
                        parts = var_line.split()
                        if len(parts) >= 2:
                            var_name = parts[1]
                            variables.append(var_name)
                elif 'Values:' in line:
                    in_header = False
                    data_start_line = i + 1
                    break

            # Parse data section
            print(f"Found {num_vars} variables, {num_points} points")
            print(f"Variables: {variables[:10]}...")  # Show first 10

            # Initialize data arrays
            for var in variables:
                data[var] = []

            # Read data (skip for now if file is huge)
            # This is a simplified parser - for production use PyLTSpice
            if num_points < 100000:  # Only parse if reasonable size
                for line in lines[data_start_line:]:
                    parts = line.strip().split()
                    if len(parts) == 2:  # Index and value
                        try:
                            val = float(parts[1])
                            var_idx = int(parts[0]) % num_vars
                            if var_idx < len(variables):
                                data[variables[var_idx]].append(val)
                        except:
                            pass

            # Convert to numpy arrays
            for var in variables:
                if data[var]:
                    data[var] = np.array(data[var])

            return data, variables

        except Exception as e:
            print(f"Error parsing raw file: {e}")
            return None, None

    def analyze_simulation(self, raw_file):
        """
        Main analysis function
        """
        print("="*70)
        print("LMR51430 SPICE Simulation Verification")
        print("="*70)
        print()

        # Load raw data
        if HAS_PYLTSPICE and raw_file.endswith('.raw'):
            print("Reading with PyLTSpice...")
            try:
                lr = RawRead(raw_file)
                time = lr.get_trace('time').get_wave()
                vout = lr.get_trace('v(vout)').get_wave()
                sw = lr.get_trace('v(sw)').get_wave()

                # Store for later use
                self.raw_data = {
                    'time': time,
                    'vout': vout,
                    'sw': sw
                }
            except Exception as e:
                print(f"PyLTSpice load failed: {e}")
                return False
        else:
            # Parse ASCII format
            data, variables = self.parse_ascii_raw(raw_file)
            if data is None:
                print("Failed to parse raw file")
                return False

            self.raw_data = data

        # Run validation tests
        passed = self.run_validation_tests()

        return passed

    def run_validation_tests(self):
        """
        Execute all validation tests
        """
        all_passed = True

        print("\n" + "="*70)
        print("VALIDATION TESTS")
        print("="*70 + "\n")

        # Test 1: Check if simulation has data
        if self.raw_data is None or not self.raw_data:
            print("[FAIL] No simulation data available")
            return False
        print("[PASS] Simulation data loaded")

        # Extract time vector
        time_keys = [k for k in self.raw_data.keys() if 'time' in k.lower()]
        if not time_keys:
            print("[FAIL] No time vector found")
            return False

        time = self.raw_data[time_keys[0]]
        if len(time) == 0:
            print("[FAIL] Empty time vector")
            return False

        print(f"[INFO] Simulation time: {time[-1]*1000:.2f} ms")
        print(f"[INFO] Data points: {len(time)}")

        # Test 2: Find and analyze VOUT
        vout_keys = [k for k in self.raw_data.keys() if 'vout' in k.lower()]
        if not vout_keys:
            print("[FAIL] No output voltage trace found")
            all_passed = False
        else:
            vout = self.raw_data[vout_keys[0]]
            if len(vout) > 0:
                vout_final = np.mean(vout[-1000:])  # Average last 1000 points
                vout_target = self.specs['VOUT_TARGET']
                tolerance = self.specs['VOUT_TOL']

                error_pct = abs(vout_final - vout_target) / vout_target * 100

                print(f"\nOutput Voltage Analysis:")
                print(f"  Target: {vout_target:.3f}V ± {tolerance*100:.1f}%")
                print(f"  Actual: {vout_final:.3f}V")
                print(f"  Error:  {error_pct:.2f}%")

                if abs(vout_final - vout_target) <= vout_target * tolerance:
                    print(f"  [PASS] Output voltage within spec")
                    self.results['vout_pass'] = True
                else:
                    print(f"  [FAIL] Output voltage out of spec!")
                    all_passed = False
                    self.results['vout_pass'] = False

                # Check ripple if enough points
                if len(vout) > 1000:
                    # Analyze last 1ms of data for ripple
                    dt = time[1] - time[0]
                    pts_per_ms = int(0.001 / dt)
                    if pts_per_ms > 10:
                        vout_steady = vout[-pts_per_ms:]
                        ripple_pp = np.max(vout_steady) - np.min(vout_steady)

                        print(f"\nRipple Analysis:")
                        print(f"  Peak-to-peak: {ripple_pp*1000:.1f}mV")
                        print(f"  Max allowed:  {self.specs['VOUT_RIPPLE_MAX']*1000:.1f}mV")

                        if ripple_pp < self.specs['VOUT_RIPPLE_MAX']:
                            print(f"  [PASS] Ripple within spec")
                        else:
                            print(f"  [FAIL] Excessive ripple!")
                            all_passed = False

        # Test 3: Check switch node
        sw_keys = [k for k in self.raw_data.keys() if 'sw' in k.lower() and 'v(' in k.lower()]
        if sw_keys:
            sw = self.raw_data[sw_keys[0]]
            if len(sw) > 1000:
                sw_steady = sw[-10000:]  # Last 10k points
                sw_max = np.max(sw_steady)
                sw_min = np.min(sw_steady)

                print(f"\nSwitch Node Analysis:")
                print(f"  Max voltage: {sw_max:.2f}V")
                print(f"  Min voltage: {sw_min:.2f}V")

                # Should swing between ~0V and VIN
                if sw_max > self.specs['VIN_NOM'] * 0.9 and sw_min < 1.0:
                    print(f"  [PASS] Switch node swinging correctly")
                else:
                    print(f"  [WARN] Switch node may not be switching properly")

        # Test 4: Estimate switching frequency
        if sw_keys and len(sw) > 1000:
            # Find zero crossings in steady state
            sw_steady = sw[-10000:]
            time_steady = time[-10000:]

            # Simple edge detection
            threshold = sw_max / 2
            crossings = np.where(np.diff(np.signbit(sw_steady - threshold)))[0]

            if len(crossings) > 10:
                # Calculate periods between rising edges
                rising = crossings[::2]  # Every other crossing
                if len(rising) > 2:
                    periods = np.diff(time_steady[rising])
                    avg_period = np.mean(periods)
                    freq_measured = 1.0 / avg_period

                    print(f"\nSwitching Frequency Analysis:")
                    print(f"  Target: {self.specs['FSW_NOM']/1e3:.0f} kHz")
                    print(f"  Measured: {freq_measured/1e3:.0f} kHz")

                    freq_error = abs(freq_measured - self.specs['FSW_NOM']) / self.specs['FSW_NOM']
                    if freq_error < 0.2:  # Within 20%
                        print(f"  [PASS] Frequency within range")
                    else:
                        print(f"  [WARN] Frequency deviation: {freq_error*100:.1f}%")

        # Summary
        print("\n" + "="*70)
        if all_passed:
            print("OVERALL RESULT: ✓ ALL TESTS PASSED")
        else:
            print("OVERALL RESULT: ✗ SOME TESTS FAILED - Review above")
        print("="*70 + "\n")

        return all_passed

    def plot_waveforms(self, output_dir="."):
        """
        Generate plots of key waveforms
        """
        if not HAS_MATPLOTLIB:
            print("Matplotlib not available for plotting")
            return

        if self.raw_data is None:
            print("No data to plot")
            return

        print("Generating waveform plots...")

        # Extract data
        time_keys = [k for k in self.raw_data.keys() if 'time' in k.lower()]
        vout_keys = [k for k in self.raw_data.keys() if 'vout' in k.lower()]
        sw_keys = [k for k in self.raw_data.keys() if 'sw' in k.lower() and 'v(' in k.lower()]

        if not time_keys or not vout_keys:
            print("Missing required traces for plotting")
            return

        time = self.raw_data[time_keys[0]]
        vout = self.raw_data[vout_keys[0]]

        # Create figure with subplots
        fig, axes = plt.subplots(3, 1, figsize=(12, 10))

        # Plot 1: Output voltage vs time
        axes[0].plot(time * 1000, vout, 'b-', linewidth=1)
        axes[0].axhline(y=self.specs['VOUT_TARGET'], color='r', linestyle='--', label='Target')
        axes[0].set_xlabel('Time (ms)')
        axes[0].set_ylabel('Output Voltage (V)')
        axes[0].set_title('LMR51430 Output Voltage - Startup and Steady State')
        axes[0].grid(True, alpha=0.3)
        axes[0].legend()

        # Plot 2: Output voltage detail (last 5ms)
        if len(time) > 1000:
            dt = time[1] - time[0]
            pts_5ms = min(int(0.005 / dt), len(time))

            axes[1].plot(time[-pts_5ms:] * 1000, vout[-pts_5ms:], 'b-', linewidth=1)
            axes[1].axhline(y=self.specs['VOUT_TARGET'], color='r', linestyle='--')
            axes[1].set_xlabel('Time (ms)')
            axes[1].set_ylabel('Output Voltage (V)')
            axes[1].set_title('Output Voltage - Steady State Detail')
            axes[1].grid(True, alpha=0.3)

        # Plot 3: Switch node if available
        if sw_keys:
            sw = self.raw_data[sw_keys[0]]
            axes[2].plot(time * 1000, sw, 'g-', linewidth=0.5)
            axes[2].set_xlabel('Time (ms)')
            axes[2].set_ylabel('SW Node Voltage (V)')
            axes[2].set_title('Switch Node Voltage')
            axes[2].grid(True, alpha=0.3)

        plt.tight_layout()

        # Save plot
        output_file = os.path.join(output_dir, 'lmr51430_verification_plots.png')
        plt.savefig(output_file, dpi=150)
        print(f"Plots saved to: {output_file}")

        # Show plot if not in batch mode
        # plt.show()  # Uncomment for interactive mode


def main():
    """
    Main entry point
    """
    parser = argparse.ArgumentParser(
        description='Verify LMR51430 SPICE simulation results'
    )
    parser.add_argument(
        'rawfile',
        nargs='?',
        default='lmr51430_raw.raw',
        help='Path to ngspice raw output file'
    )
    parser.add_argument(
        '--plot',
        action='store_true',
        help='Generate waveform plots'
    )
    parser.add_argument(
        '--output-dir',
        default='.',
        help='Directory for output files'
    )

    args = parser.parse_args()

    # Check if raw file exists
    if not os.path.exists(args.rawfile):
        print(f"Error: Raw file not found: {args.rawfile}")
        print("\nRun ngspice first:")
        print("  ngspice -b -r output.raw LMR51430_test.cir")
        return 1

    # Create validator
    validator = LMR51430Validator()

    # Analyze
    passed = validator.analyze_simulation(args.rawfile)

    # Plot if requested
    if args.plot:
        validator.plot_waveforms(args.output_dir)

    # Return exit code
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
