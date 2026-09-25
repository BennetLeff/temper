// Append to the frozen Rev26 audit_aux.rs and compile with rustc --test.
// Reads the two compiled netlists named by REV26_NET and REV28_NET.

#[test]
fn compiled_link_clear_is_the_only_rev26_connectivity_change() {
    let old_path = std::env::var("REV26_NET").expect("set REV26_NET");
    let new_path = std::env::var("REV28_NET").expect("set REV28_NET");
    let old =
        graph(&fs::read_to_string(old_path).expect("Rev26 netlist")).expect("parse Rev26 netlist");
    let new =
        graph(&fs::read_to_string(new_path).expect("Rev28 netlist")).expect("parse Rev28 netlist");

    let additions: BTreeMap<Pin, String> = [
        (
            "protection.link_good_input_pd",
            "1",
            "HOT_LINK_GOOD_EXTERNAL",
        ),
        ("protection.link_good_input_pd", "2", "PFC_BUS_MINUS"),
        ("protection.link_clear_and", "1", "clear_core_ok"),
        ("protection.link_clear_and", "2", "HOT_LINK_GOOD_EXTERNAL"),
        ("protection.link_clear_and", "3", "PFC_BUS_MINUS"),
        ("protection.link_clear_and", "4", "clear_ok"),
        ("protection.link_clear_and", "5", "logic5"),
        ("protection.link_clear_bypass", "1", "logic5"),
        ("protection.link_clear_bypass", "2", "PFC_BUS_MINUS"),
        ("protection.clear_ok_pd", "1", "clear_ok"),
        ("protection.clear_ok_pd", "2", "PFC_BUS_MINUS"),
    ]
    .into_iter()
    .map(|(id, pin, net)| ((id.to_string(), pin.to_string()), net.to_string()))
    .collect();
    let added_ids: BTreeSet<String> = additions.keys().map(|(id, _)| id.clone()).collect();
    assert_eq!(old.components.len(), 150);
    assert_eq!(added_ids.len(), 4);
    assert_eq!(new.components.len(), 154);
    assert_eq!(
        new.components,
        old.components.union(&added_ids).cloned().collect()
    );

    let actual_additions: BTreeMap<Pin, String> = new
        .pins
        .iter()
        .filter(|(pin, _)| added_ids.contains(&pin.0))
        .map(|(pin, net)| (pin.clone(), net.clone()))
        .collect();
    assert_eq!(
        actual_additions, additions,
        "new gate, bias and bypass pins"
    );
    assert_eq!(new.pins.len(), old.pins.len() + additions.len());

    let health_output = ("protection.health".to_string(), "8".to_string());
    for (pin, net) in &old.pins {
        let expected = if *pin == health_output {
            "clear_core_ok"
        } else {
            net.as_str()
        };
        assert_eq!(
            new.pins.get(pin).map(String::as_str),
            Some(expected),
            "existing Rev26 pin changed: {pin:?}"
        );
    }

    assert_eq!(
        pin_group(&new, "clear_core_ok"),
        [
            health_output,
            ("protection.link_clear_and".into(), "1".into())
        ]
        .into_iter()
        .collect()
    );
    assert_eq!(
        pin_group(&new, "clear_ok"),
        [
            ("protection.link_clear_and".into(), "4".into()),
            ("protection.clear_ok_pd".into(), "1".into()),
            ("protection.latch".into(), "1".into()),
            ("protection.enable_and".into(), "2".into()),
        ]
        .into_iter()
        .collect()
    );
}
