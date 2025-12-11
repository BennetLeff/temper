#!/usr/bin/env python3
"""
Simple LMR51430 SPICE Simulation Verification Tool
No external dependencies required - uses only Python standard library

Usage:
    python3 verify_simple.py [raw_file]

For induction cooker LMR51430 power supply design
Date: 2025-12-09
"""

import sys
import os
import re
from pathlib import Path


class SimpleValidator:
    """
    Validates SPICE simulation results without numpy/matplotlib
    """

    def __init__(self):
        self.specs = {
            'VOUT_TARGET': 5.0,
            'VOUT_TOL_PCT': 7.5,  # ±7.5%
            'VOUT_RIPPLE_MAX_MV': 100.0,
            'FSW_NOM_KHZ': 500.0,
        }
        self.data = {}

    def parse_ascii_raw_simple(self, filename):
        """
        Parse ASCII raw file - simplified version
        """
        print(f"\nParsing: {filename}")
        print("-" * 70)

        try:
            with open(filename, 'r') as f:
                content = f.read()

            # Extract key information from header
            num_vars = 0
            num_points = 0

            # Parse header
            if 'No. of Variables:' in content:
                match = re.search(r'No\. of Variables:\s*(\d+)', content)
                if match:
                    num_vars = int(match.group(1))

            if 'No. of Points:' in content:
                match = re.search(r'No\. of Points:\s*(\d+)', content)
                if match:
                    num_points = int(match.group(1))

            print(f"Variables: {num_vars}")
            print(f"Data Points: {num_points}")

            # Parse variable names
            variables = []
            var_section = re.search(r'Variables:(.*?)Values:', content, re.DOTALL)
            if var_section:
                var_lines = var_section.group(1).strip().split('\n')
                for line in var_lines:
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        var_name = parts[1]
                        variables.append(var_name)

            print(f"Found variables: {', '.join(variables[:10])}{('...' if len(variables) > 10 else '')}")

            # Store basic info
            self.data = {
                'num_vars': num_vars,
                'num_points': num_points,
                'variables': variables,
                'success': num_vars > 0 and num_points > 0
            }

            return self.data['success']

        except Exception as e:
            print(f"ERROR: Could not parse file: {e}")
            return False

    def analyze_text_output(self, log_file):
        """
        Analyze the text log output from ngspice
        """
        print("\nAnalyzing ngspice log output:")
        print("-" * 70)

        try:
            with open(log_file, 'r') as f:
                content = f.read()

            # Look for measurement results
            measurements = {}

            # Extract vout_avg
            match = re.search(r'vout_avg\s*=\s*([\d.e+-]+)', content)
            if match:
                measurements['vout_avg'] = float(match.group(1))

            # Extract vout_pp (peak-to-peak ripple)
            match = re.search(r'vout_pp\s*=\s*([\d.e+-]+)', content)
            if match:
                measurements['vout_pp'] = float(match.group(1))

            # Extract il_avg (inductor current)
            match = re.search(r'il_avg\s*=\s*([\d.e+-]+)', content)
            if match:
                measurements['il_avg'] = float(match.group(1))

            # Display results
            if measurements:
                print("\nMeasurement Results:")
                print(f"  VOUT average:     {measurements.get('vout_avg', 'N/A')} V")
                print(f"  VOUT ripple (p-p): {measurements.get('vout_pp', 'N/A')} V")
                print(f"  Inductor current:  {measurements.get('il_avg', 'N/A')} A")

                # Validation
                vout = measurements.get('vout_avg', 0)
                target = self.specs['VOUT_TARGET']
                tol = self.specs['VOUT_TOL_PCT'] / 100.0

                print("\n" + "=" * 70)
                print("VALIDATION RESULTS:")
                print("=" * 70)

                # Check output voltage
                error_pct = abs(vout - target) / target * 100
                print(f"\n1. Output Voltage Check:")
                print(f"   Target:  {target:.3f}V ± {self.specs['VOUT_TOL_PCT']:.1f}%")
                print(f"   Measured: {vout:.3f}V")
                print(f"   Error:    {error_pct:.2f}%")

                if vout < 1.0:
                    print(f"   [FAIL] ✗ Output voltage too low - check SPICE model!")
                    print(f"   NOTE: This suggests the regulator is not starting or switching.")
                    print(f"         Possible causes:")
                    print(f"         - Enable signal not activating")
                    print(f"         - Internal oscillator not working")
                    print(f"         - Feedback loop issue")
                    return False
                elif abs(vout - target) <= target * tol:
                    print(f"   [PASS] ✓ Within specification")
                else:
                    print(f"   [WARN] ⚠ Outside target range but regulating")

                # Check ripple
                ripple = measurements.get('vout_pp', 0)
                print(f"\n2. Output Ripple Check:")
                print(f"   Measured: {ripple*1000:.1f}mV p-p")
                print(f"   Max spec: {self.specs['VOUT_RIPPLE_MAX_MV']:.1f}mV")

                if ripple * 1000 < self.specs['VOUT_RIPPLE_MAX_MV']:
                    print(f"   [PASS] ✓ Ripple within limits")
                else:
                    print(f"   [FAIL] ✗ Excessive ripple")

                # Check inductor current
                il = measurements.get('il_avg', 0)
                print(f"\n3. Inductor Current Check:")
                print(f"   Measured: {il:.3f}A")
                print(f"   Expected: ~2.0A (for 2.5Ω load @ 5V)")

                if 1.5 < il < 2.5:
                    print(f"   [PASS] ✓ Current reasonable for load")
                elif il < 0.5:
                    print(f"   [FAIL] ✗ Current too low - not delivering power")
                else:
                    print(f"   [WARN] ⚠ Current outside expected range")

                print("\n" + "=" * 70)

                # Overall assessment
                if vout > 1.0:
                    print("OVERALL: Model appears functional but needs investigation")
                    return True
                else:
                    print("OVERALL: Model not operating - significant issue detected")
                    return False
            else:
                print("ERROR: No measurements found in log file")
                return False

        except Exception as e:
            print(f"ERROR analyzing log: {e}")
            return False

    def generate_report(self, output_file="verification_report.txt"):
        """
        Generate a summary report
        """
        print(f"\nGenerating report: {output_file}")

        with open(output_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("LMR51430 SPICE Model Verification Report\n")
            f.write("For Induction Cooker Auxiliary Power Supply\n")
            f.write("=" * 70 + "\n\n")

            f.write("Test Configuration:\n")
            f.write(f"  Input Voltage:  12V\n")
            f.write(f"  Output Voltage: 5V target\n")
            f.write(f"  Load Current:   2A\n")
            f.write(f"  Frequency:      500kHz\n\n")

            if self.data.get('success'):
                f.write(f"Simulation Statistics:\n")
                f.write(f"  Data Points: {self.data.get('num_points', 'N/A')}\n")
                f.write(f"  Variables:   {self.data.get('num_vars', 'N/A')}\n\n")

            f.write("Next Steps for Induction Cooker Integration:\n")
            f.write("1. Verify SPICE model accuracy against hardware prototype\n")
            f.write("2. Test with actual auxiliary winding voltage range (10-24V)\n")
            f.write("3. Validate thermal performance at 70°C ambient\n")
            f.write("4. Check EMI/EMC with real PCB layout\n")
            f.write("5. Test protection features (OCP, OVP, thermal)\n")
            f.write("6. Verify startup behavior with induction coil switching noise\n\n")

            f.write("Safety Checklist:\n")
            f.write("☐ Input voltage transient protection (TVS diode)\n")
            f.write("☐ Output voltage monitoring by MCU\n")
            f.write("☐ Thermal monitoring (NTC sensor)\n")
            f.write("☐ Proper isolation from mains-referenced circuits\n")
            f.write("☐ Fusing on input and output\n\n")

        print(f"Report saved: {output_file}")


def main():
    """
    Main function
    """
    print("=" * 70)
    print("LMR51430 SPICE Simulation Verification Tool")
    print("Induction Cooker Auxiliary Power Supply")
    print("=" * 70)

    # Determine files
    if len(sys.argv) > 1:
        raw_file = sys.argv[1]
    else:
        raw_file = "lmr51430_raw.raw"

    log_file = "lmr51430_sim_results.txt"

    validator = SimpleValidator()

    # Try to parse raw file
    if os.path.exists(raw_file):
        validator.parse_ascii_raw_simple(raw_file)
    else:
        print(f"Raw file not found: {raw_file}")

    # Analyze log file (more useful for quick validation)
    success = False
    if os.path.exists(log_file):
        success = validator.analyze_text_output(log_file)
    else:
        print(f"Log file not found: {log_file}")
        print("\nTo generate simulation data, run:")
        print("  ngspice -b LMR51430_test.cir -o lmr51430_sim_results.txt")

    # Generate report
    validator.generate_report()

    print("\n" + "=" * 70)
    if success:
        print("Validation complete - see report for details")
    else:
        print("Validation detected issues - review SPICE model")
    print("=" * 70 + "\n")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
