/// IPC-2221 creepage/clearance table.
///
/// Encodes the exact voltage bracket boundaries from the canonical PCB design
/// standard.  The table is monotonic: each bracket's max voltage is strictly
/// greater than the previous, and each clearance is >= the previous.
///
/// Boundaries sourced from `router_v6/creepage_check.py:382-433`:
///   0-15V → 0.13mm,  16-30V → 0.25mm,  31-50V → 0.50mm,
///   51-100V → 0.80mm, 101-150V → 1.25mm, 151-170V → 1.60mm,
///   171-250V → 3.20mm, 251-300V → 6.40mm, 301-600V → 8.00mm,
///   601-1000V → 12.00mm

/// A single voltage bracket: voltages up to `max_voltage` require at least
/// `clearance_mm` creepage distance.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CreepageBracket {
    pub max_voltage: f64,
    pub clearance_mm: f64,
}

/// IPC-2221 bracket table — ordered by ascending max_voltage.
pub const IPC2221_BRACKETS: [CreepageBracket; 10] = [
    CreepageBracket { max_voltage: 15.0, clearance_mm: 0.13 },
    CreepageBracket { max_voltage: 30.0, clearance_mm: 0.25 },
    CreepageBracket { max_voltage: 50.0, clearance_mm: 0.50 },
    CreepageBracket { max_voltage: 100.0, clearance_mm: 0.80 },
    CreepageBracket { max_voltage: 150.0, clearance_mm: 1.25 },
    CreepageBracket { max_voltage: 170.0, clearance_mm: 1.60 },
    CreepageBracket { max_voltage: 250.0, clearance_mm: 3.20 },
    CreepageBracket { max_voltage: 300.0, clearance_mm: 6.40 },
    CreepageBracket { max_voltage: 600.0, clearance_mm: 8.00 },
    CreepageBracket { max_voltage: 1000.0, clearance_mm: 12.00 },
];

/// Return the required creepage distance (mm) for a given working voltage.
///
/// Uses the first bracket whose max_voltage covers the input.  Voltages
/// above the highest bracket (1000V) return the max clearance (12.0mm).
pub fn required_clearance(voltage: f64) -> f64 {
    for bracket in &IPC2221_BRACKETS {
        if voltage <= bracket.max_voltage {
            return bracket.clearance_mm;
        }
    }
    // Above highest bracket — return the maximum defined clearance
    IPC2221_BRACKETS.last().map(|b| b.clearance_mm).unwrap_or(12.0)
}

/// Verify that the bracket table is monotonic:
/// - Each max_voltage > previous
/// - Each clearance_mm >= previous
pub fn verify_monotonic() -> Result<(), String> {
    for i in 1..IPC2221_BRACKETS.len() {
        let prev = &IPC2221_BRACKETS[i - 1];
        let curr = &IPC2221_BRACKETS[i];
        if curr.max_voltage <= prev.max_voltage {
            return Err(format!(
                "bracket {} max_voltage ({}) <= bracket {} max_voltage ({})",
                i, curr.max_voltage, i - 1, prev.max_voltage
            ));
        }
        if curr.clearance_mm < prev.clearance_mm {
            return Err(format!(
                "bracket {} clearance ({}) < bracket {} clearance ({})",
                i, curr.clearance_mm, i - 1, prev.clearance_mm
            ));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_monotonic_by_construction() {
        verify_monotonic().expect("IPC-2221 brackets must be monotonic");
    }

    #[test]
    fn test_required_clearance_known_values() {
        assert!((required_clearance(0.0) - 0.13).abs() < 1e-10);
        assert!((required_clearance(10.0) - 0.13).abs() < 1e-10);
        assert!((required_clearance(15.0) - 0.13).abs() < 1e-10);
        assert!((required_clearance(16.0) - 0.25).abs() < 1e-10);
        assert!((required_clearance(30.0) - 0.25).abs() < 1e-10);
        assert!((required_clearance(110.0) - 1.25).abs() < 1e-10);
        assert!((required_clearance(230.0) - 3.20).abs() < 1e-10);
        assert!((required_clearance(250.0) - 3.20).abs() < 1e-10);
        assert!((required_clearance(251.0) - 6.40).abs() < 1e-10);
        assert!((required_clearance(500.0) - 8.00).abs() < 1e-10);
        assert!((required_clearance(600.0) - 8.00).abs() < 1e-10);
        assert!((required_clearance(800.0) - 12.00).abs() < 1e-10);
        assert!((required_clearance(1500.0) - 12.00).abs() < 1e-10);
    }

    #[test]
    fn test_required_clearance_edge_boundaries() {
        assert!((required_clearance(50.0) - 0.50).abs() < 1e-10);
        assert!((required_clearance(51.0) - 0.80).abs() < 1e-10);
        assert!((required_clearance(100.0) - 0.80).abs() < 1e-10);
        assert!((required_clearance(101.0) - 1.25).abs() < 1e-10);
        assert!((required_clearance(170.0) - 1.60).abs() < 1e-10);
        assert!((required_clearance(171.0) - 3.20).abs() < 1e-10);
        assert!((required_clearance(300.0) - 6.40).abs() < 1e-10);
        assert!((required_clearance(301.0) - 8.00).abs() < 1e-10);
        assert!((required_clearance(1000.0) - 12.00).abs() < 1e-10);
        assert!((required_clearance(1001.0) - 12.00).abs() < 1e-10);
    }
}
