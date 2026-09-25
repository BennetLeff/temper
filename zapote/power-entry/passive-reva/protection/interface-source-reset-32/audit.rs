use std::fs;

fn net<'a>(text: &'a str, code: &str) -> &'a str {
    let marker = format!("(net (code ");
    for chunk in text.split(&marker).skip(1) {
        if chunk.starts_with(&format!("\"{}\") (name ", code)) {
            return chunk.split("\n    (net ").next().unwrap_or(chunk);
        }
    }
    panic!("missing net code {code}");
}

fn has(net: &str, refdes: &str, pin: &str) -> bool {
    net.contains(&format!("(node (ref \"{refdes}\") (pin \"{pin}\")"))
}

fn main() {
    let text = fs::read_to_string("build/default.net").expect("Atopile netlist");
    let power = net(&text, "1");
    let ground = net(&text, "2");
    let heartbeat = net(&text, "3");
    let reset_good = net(&text, "4");
    let watchdog_good = net(&text, "5");
    let wdi = net(&text, "6");
    let cwd = net(&text, "7");

    for (pin, n) in [("1", power), ("3", power), ("5", power)] {
        assert!(has(n, "U1", pin), "TPS3431 pin {pin} must be SELV3V3");
    }
    assert!(has(power, "U2", "5"), "LVC1G17 VCC must be SELV3V3");
    for (pin, n) in [("4", ground), ("9", ground)] {
        assert!(has(n, "U1", pin), "TPS3431 pin {pin} must be ground");
    }
    assert!(has(ground, "U2", "3"), "LVC1G17 GND must be SELV_GND");
    assert!(has(heartbeat, "U2", "2") && has(heartbeat, "U7", "1"));
    assert!(has(reset_good, "U9", "1"));
    assert!(has(watchdog_good, "U1", "7") && has(watchdog_good, "U1", "8"));
    assert!(has(watchdog_good, "U6", "2"));
    assert!(has(cwd, "U1", "2") && has(cwd, "U3", "1"));
    assert!(has(wdi, "U1", "6") && has(wdi, "U2", "4") && has(wdi, "U8", "1"));
    assert!(!heartbeat.contains("(node (ref \"U1\")"), "ESP heartbeat must not directly drive TPS WDI");
    assert!(!reset_good.contains("(node (ref \"U1\")"));
    assert!(ground.contains("(node (ref \"U4\") (pin \"2\")"));
    println!("PASS: TPS3431, LVC1G17 buffer, WDI, watchdog output and reset-good pin/net checks");
}
