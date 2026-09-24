//! Source-bound service-port screen. The verdict is not appliance acceptance.
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::Command;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Verdict {
    Rejected,
    Indeterminate,
}

impl Verdict {
    fn parse(value: &str) -> Result<Self, String> {
        match value {
            "rejected" => Ok(Self::Rejected),
            "indeterminate" => Ok(Self::Indeterminate),
            _ => Err(format!("unknown verdict: {value}")),
        }
    }
}

#[derive(Debug)]
pub struct Case<'a> {
    pub name: &'a str,
    tx: &'a str,
    rx: &'a str,
    en: &'a str,
    io0: &'a str,
    supply_v: f32,
    return_present: bool,
    en_released: bool,
    io0_released: bool,
    claimed_isolated: bool,
    barrier_present: bool,
    backfeed_blocked: bool,
    extra_gpio_owner: bool,
    access_isolated_discharged: bool,
    reset_stops_pfc: bool,
    reset_stops_inverter: bool,
    no_auto_rearm: bool,
    expander_retained_request: bool,
    pub expected: Verdict,
}

pub struct Assessment {
    pub verdict: Verdict,
    pub reason: &'static str,
}

pub fn evaluate(case: &Case<'_>) -> Assessment {
    let rejected = |reason| Assessment {
        verdict: Verdict::Rejected,
        reason,
    };
    let indeterminate = |reason| Assessment {
        verdict: Verdict::Indeterminate,
        reason,
    };
    if case.tx != "43" || case.rx != "44" || case.en != "3" || case.io0 != "27" {
        return rejected("UART direction or EN/IO0 module pad does not match source");
    }
    if case.extra_gpio_owner {
        return rejected("duplicate GPIO owner");
    }
    if !case.return_present || !(3.135..=3.465).contains(&case.supply_v) {
        return rejected("SELV 3V3 or its return is absent/out of declared range");
    }
    if !case.en_released || !case.io0_released {
        return rejected("EN or IO0 remains low after programming/reset");
    }
    if case.claimed_isolated && !case.barrier_present {
        return rejected("isolation claim has no implemented barrier");
    }
    if !case.backfeed_blocked {
        return rejected("programmer can backfeed unpowered target I/O");
    }
    if case.access_isolated_discharged {
        return indeterminate(
            "isolation/discharge claim lacks independent physical record and review identity",
        );
    }
    if case.reset_stops_pfc != case.reset_stops_inverter {
        return rejected("programmer reset leaves one power stage running");
    }
    if case.reset_stops_pfc && case.reset_stops_inverter && !case.no_auto_rearm {
        return rejected("reset path allows automatic rearm");
    }
    if case.expander_retained_request {
        return indeterminate("retained expander output is not bounded by physical stop evidence");
    }
    if case.reset_stops_pfc && case.reset_stops_inverter && case.no_auto_rearm {
        return indeterminate("both-stage-stop claim lacks measured waveform and review identity");
    }
    indeterminate("service reset energy and stop behavior not established")
}

fn boolean(value: &str) -> Result<bool, String> {
    match value {
        "true" => Ok(true),
        "false" => Ok(false),
        _ => Err(format!("invalid boolean: {value}")),
    }
}

pub fn parse_cases(input: &str) -> Result<Vec<Case<'_>>, String> {
    let mut lines = input.lines();
    let header = lines.next().ok_or("missing header")?;
    if header.split('\t').count() != 19 || !header.starts_with("case\ttx_gpio\trx_gpio") {
        return Err("invalid case header".into());
    }
    let mut cases = Vec::new();
    for (line_no, line) in lines.enumerate() {
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() != 19 {
            return Err(format!("line {} has {} columns", line_no + 2, f.len()));
        }
        cases.push(Case {
            name: f[0],
            tx: f[1],
            rx: f[2],
            en: f[3],
            io0: f[4],
            supply_v: f[5]
                .parse()
                .map_err(|_| format!("bad supply on line {}", line_no + 2))?,
            return_present: boolean(f[6])?,
            en_released: boolean(f[7])?,
            io0_released: boolean(f[8])?,
            claimed_isolated: boolean(f[9])?,
            barrier_present: boolean(f[10])?,
            backfeed_blocked: boolean(f[11])?,
            extra_gpio_owner: boolean(f[12])?,
            access_isolated_discharged: boolean(f[13])?,
            reset_stops_pfc: boolean(f[14])?,
            reset_stops_inverter: boolean(f[15])?,
            no_auto_rearm: boolean(f[16])?,
            expander_retained_request: boolean(f[17])?,
            expected: Verdict::parse(f[18])?,
        });
    }
    if cases.is_empty() {
        return Err("empty case matrix".into());
    }
    Ok(cases)
}

/// Conflicts among existing cooker electrical and firmware claims only.
pub fn pin_conflicts(ledger: &str) -> Result<Vec<String>, String> {
    let mut claims: BTreeMap<&str, BTreeSet<(&str, &str)>> = BTreeMap::new();
    let mut lines = ledger.lines();
    if lines.next()
        != Some("authority\tgpio\tmodule_pad\trole\tdirection\tdomain\tboot_or_reset\tstatus")
    {
        return Err("invalid pin ledger header".into());
    }
    for line in lines {
        let f: Vec<&str> = line.split('\t').collect();
        if f.len() != 8 {
            return Err("invalid pin ledger row".into());
        }
        if f[0] == "legacy-ato" || f[0] == "firmware" {
            claims.entry(f[1]).or_default().insert((f[0], f[3]));
        }
    }
    Ok(claims
        .into_iter()
        .filter_map(|(gpio, rows)| {
            let roles: BTreeSet<_> = rows.iter().map(|(_, role)| *role).collect();
            (roles.len() > 1).then(|| {
                format!(
                    "{gpio}: {}",
                    rows.iter()
                        .map(|(owner, role)| format!("{owner}={role}"))
                        .collect::<Vec<_>>()
                        .join(", ")
                )
            })
        })
        .collect())
}

pub fn verify_sources(repo: &Path, manifest: &str) -> Result<(), String> {
    const REQUIRED: [&str; 6] = [
        "elec/src/modules.ato",
        "elec/src/components.ato",
        "elec/src/main.ato",
        "firmware/components/hal/include/temper_pins.h",
        "zapote/power-entry/passive-reva/protection/interface-integration-38/ESP-PIN-FIT.md",
        "zapote/power-entry/passive-reva/protection/interface-integration-38/ESP-PIN-INVENTORY.md",
    ];
    let mut count = 0;
    let mut seen = BTreeSet::new();
    for line in manifest.lines() {
        let (expected, path) = line.split_once("  ").ok_or("bad source manifest row")?;
        if expected.len() != 64
            || !expected.bytes().all(|c| c.is_ascii_hexdigit())
            || path.starts_with('/')
            || path.contains("..")
        {
            return Err(format!("invalid source identity: {line}"));
        }
        if !REQUIRED.contains(&path) || !seen.insert(path) {
            return Err(format!("unexpected or duplicate source: {path}"));
        }
        let output = Command::new("shasum")
            .arg("-a")
            .arg("256")
            .arg(repo.join(path))
            .output()
            .map_err(|err| format!("shasum failed for {path}: {err}"))?;
        if !output.status.success() {
            return Err(format!("cannot hash {path}"));
        }
        let digest = String::from_utf8(output.stdout).map_err(|_| "bad digest output")?;
        if digest.split_whitespace().next() != Some(expected) {
            return Err(format!("STALE source: {path}"));
        }
        count += 1;
    }
    if count != REQUIRED.len() {
        return Err(format!("expected six source identities, found {count}"));
    }
    for (path, snippets) in [
        (
            "elec/src/modules.ato",
            &[
                "usb_dn ~ mcu.IO19",
                "usb_dp ~ mcu.IO20",
                "fault_status_in.line ~ mcu.IO17",
                "uart.tx ~ mcu.TXD0",
                "uart.rx ~ mcu.RXD0",
                "r_boot.p2 ~ mcu.IO0",
                "btn_reset.p1 ~ mcu.EN",
            ][..],
        ),
        (
            "elec/src/components.ato",
            &[
                "signal TXD0 ~ pin 37",
                "signal RXD0 ~ pin 36",
                "signal EN ~ pin 3",
                "signal IO0 ~ pin 27",
            ][..],
        ),
        (
            "firmware/components/hal/include/temper_pins.h",
            &[
                "#define PIN_RELAY_BYPASS        19",
                "#define PIN_FAULT_OUT           20",
                "#define PIN_LED_FAULT           17",
                "#define PIN_UART_TX             43",
                "#define PIN_UART_RX             44",
            ][..],
        ),
    ] {
        let content = std::fs::read_to_string(repo.join(path)).map_err(|err| err.to_string())?;
        for snippet in snippets {
            if !content.contains(snippet) {
                return Err(format!("source claim missing from {path}: {snippet}"));
            }
        }
    }
    Ok(())
}

fn main() {
    let repo = std::env::args().nth(1).unwrap_or_else(|| ".".into());
    let root = Path::new(&repo);
    let local = root.join("zapote/programming-ui");
    let result = (|| -> Result<(), String> {
        verify_sources(
            root,
            &std::fs::read_to_string(local.join("sources.sha256")).map_err(|e| e.to_string())?,
        )?;
        let ledger =
            std::fs::read_to_string(local.join("pin-ledger.tsv")).map_err(|e| e.to_string())?;
        let conflicts = pin_conflicts(&ledger)?;
        let cases_text =
            std::fs::read_to_string(local.join("service-cases.tsv")).map_err(|e| e.to_string())?;
        let cases = parse_cases(&cases_text)?;
        println!("SOURCE_LOCK PASS: 6 files");
        for conflict in &conflicts {
            println!("PIN_CONFLICT {conflict}");
        }
        for case in &cases {
            let result = evaluate(case);
            if result.verdict != case.expected {
                return Err(format!(
                    "{} expected {:?}, got {:?}",
                    case.name, case.expected, result.verdict
                ));
            }
            println!("CASE {} {:?}: {}", case.name, result.verdict, result.reason);
        }
        let expected_conflicts = [
            "16: firmware=RTD_CS2_RESERVED, legacy-ato=RELAY_CTRL",
            "17: firmware=LED_FAULT, legacy-ato=FAULT_STATUS_IN",
            "19: firmware=RELAY_BYPASS, legacy-ato=USB_DN",
            "20: firmware=FAULT_OUT, legacy-ato=USB_DP",
        ];
        if !expected_conflicts
            .iter()
            .all(|row| conflicts.iter().any(|observed| observed == row))
        {
            return Err("required source conflicts disappeared; review ledger".into());
        }
        Err(
            "BASELINE BLOCKED: pin conflicts and service connector/energy evidence unresolved"
                .into(),
        )
    })();
    if let Err(err) = result {
        eprintln!("{err}");
        std::process::exit(2);
    }
}
