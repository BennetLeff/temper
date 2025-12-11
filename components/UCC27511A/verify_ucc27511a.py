#!/usr/bin/env python3
"""
UCC27511A SPICE Simulation Verification Tool
Simple verification using only Python standard library

Usage:
    ngspice -b UCC27511A_working_test.cir -o results.txt
    python3 verify_ucc27511a.py results.txt

For induction cooker IGBT gate driver design
Date: 2025-12-09
"""

import sys
import re


def parse_results(filename):
    """Parse ngspice output file"""
    try:
        with open(filename, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"ERROR: File '{filename}' not found")
        return None
    
    measurements = {}
    
    # Extract measurements
    patterns = {
        'v_gate_high': r'v_gate_high\s*=\s*([\d.eE+-]+)',
        'v_gate_low': r'v_gate_low\s*=\s*([\d.eE+-]+)',
        'v_outl_high': r'v_outl_high\s*=\s*([\d.eE+-]+)',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            measurements[key] = float(match.group(1))
    
    # Check for errors
    errors = re.findall(r'Error:.*', content)
    warnings = re.findall(r'Warning:.*', content)
    
    return {
        'measurements': measurements,
        'errors': errors,
        'warnings': warnings,
        'content': content
    }


def validate_measurements(data):
    """Validate measured values against specifications"""
    
    if not data or 'measurements' not in data:
        return False, []
    
    measurements = data['measurements']
    results = []
    all_pass = True
    
    # Expected values for 12V supply
    checks = [
        ('v_gate_high', 11.0, 12.5, 'Gate voltage HIGH'),
        ('v_gate_low', -0.5, 0.5, 'Gate voltage LOW'),
    ]
    
    for key, min_val, max_val, description in checks:
        if key in measurements:
            value = measurements[key]
            passed = min_val <= value <= max_val
            status = "PASS" if passed else "FAIL"
            results.append({
                'parameter': description,
                'value': value,
                'min': min_val,
                'max': max_val,
                'passed': passed,
                'status': status
            })
            if not passed:
                all_pass = False
        else:
            results.append({
                'parameter': description,
                'value': None,
                'passed': False,
                'status': 'MISSING'
            })
            all_pass = False
    
    return all_pass, results


def print_report(data, results, all_pass):
    """Print validation report"""
    
    print("\n" + "="*70)
    print("  UCC27511A SPICE Simulation Verification Report")
    print("="*70)
    
    if data['measurements']:
        print("\nMeasurements:")
        print("-" * 70)
        for key, value in data['measurements'].items():
            print(f"  {key:20s} = {value:12.6e}")
    
    print("\nValidation Results:")
    print("-" * 70)
    
    for r in results:
        status_symbol = "✓" if r['passed'] else "✗"
        if r['value'] is not None:
            print(f"  [{r['status']}] {status_symbol} {r['parameter']}: " 
                  f"{r['value']:.3f}V (range: {r['min']:.1f}V to {r['max']:.1f}V)")
        else:
            print(f"  [{r['status']}] {status_symbol} {r['parameter']}: NOT MEASURED")
    
    if data['errors']:
        print("\nErrors Found:")
        print("-" * 70)
        for error in data['errors'][:5]:  # Show first 5
            print(f"  {error}")
    
    if data['warnings']:
        print(f"\nWarnings: {len(data['warnings'])} found")
    
    print("\n" + "="*70)
    if all_pass:
        print("  STATUS: ✓ ALL TESTS PASSED")
    else:
        print("  STATUS: ✗ SOME TESTS FAILED")
    print("="*70 + "\n")
    
    return all_pass


def main():
    """Main execution"""
    
    if len(sys.argv) < 2:
        # Look for default file
        default_files = ['working_test_results.txt', 'ucc27511a_sim_results.txt', 'results.txt']
        filename = None
        for f in default_files:
            if os.path.exists(f):
                filename = f
                break
        
        if filename is None:
            print("Usage: python3 verify_ucc27511a.py <results_file>")
            print("\nRun simulation first:")
            print("  ngspice -b UCC27511A_working_test.cir -o results.txt")
            sys.exit(1)
    else:
        filename = sys.argv[1]
    
    print(f"Verifying: {filename}")
    
    data = parse_results(filename)
    if data is None:
        sys.exit(1)
    
    all_pass, results = validate_measurements(data)
    success = print_report(data, results, all_pass)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    import os
    main()
