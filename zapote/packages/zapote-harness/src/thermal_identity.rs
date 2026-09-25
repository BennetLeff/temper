//! Exact reviewed geometry transfer; thermal applicability remains separate.
use std::path::Path;

/// Reuse historical local thermal geometry only across the reviewed boost
/// identity correction. Callers must independently bind each model's heat inputs.
/// This does not transfer MOSFET heat or qualify assembly
/// applicability. Original decks, reports and their strict replays stay intact.
pub(crate) fn reviewed_boost_identity_input(
    current: &[u8],
    root: &Path,
) -> anyhow::Result<(Vec<u8>, String)> {
    let retained = std::fs::read(root.join("native.json"))?;
    let mut old: serde_json::Value = serde_json::from_slice(&retained)?;
    let mut now: serde_json::Value = serde_json::from_slice(current)?;
    for value in [&old, &now] {
        let board = value["board_file_utf8"]
            .as_str()
            .ok_or_else(|| anyhow::anyhow!("embedded board missing"))?;
        anyhow::ensure!(
            value["board_sha256"].as_str()
                == Some(crate::runner::digest(board.as_bytes()).as_str()),
            "native embedded board hash mismatch"
        );
    }
    for data in [current, retained.as_slice()] {
        anyhow::ensure!(
            zapote_drc::native_binding::validate(std::str::from_utf8(data)?).status
                == zapote_core::Status::Pass,
            "unbound native in historical shunt transfer"
        );
    }
    anyhow::ensure!(
        old["board_sha256"] == "b1e06afbf0e9a8b41a3bbbbd046abeb5495e9b42f3fc07e1b312095bc7e97583",
        "unreviewed historical shunt board"
    );
    anyhow::ensure!(
        old["extractor_sha256"]
            == "42b771f81f46b3054c26d3e3f80c79ab02a78964e048f2db29e88fd2cf2bea8b",
        "unreviewed historical extractor"
    );
    if current == retained {
        return Ok((retained, String::new()));
    }
    let board = old["board_file_utf8"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("old board bytes missing"))?;
    let mut transferred = board.to_owned();
    for property in ["Value", "MPN"] {
        let from = format!("(property \"{property}\" \"STW65N65DM2\"");
        let to = format!("(property \"{property}\" \"STW65N65DM2AG\"");
        anyhow::ensure!(
            board.matches(&from).count() == 1,
            "historical shunt transfer requires exactly one reviewed boost {property} property"
        );
        transferred = transferred.replace(&from, &to);
    }
    anyhow::ensure!(
        now["board_file_utf8"].as_str() == Some(transferred.as_str()),
        "historical shunt transfer permits only reviewed boost Value/MPN changes"
    );
    for (value, expected) in [(&mut old, "STW65N65DM2"), (&mut now, "STW65N65DM2AG")] {
        let components = value["components"]
            .as_array_mut()
            .ok_or_else(|| anyhow::anyhow!("components missing"))?;
        let mut matches = components.iter_mut().filter(|c| c["id"] == "q_boost");
        let boost = matches
            .next()
            .ok_or_else(|| anyhow::anyhow!("boost missing"))?;
        anyhow::ensure!(boost["mpn"] == expected, "unreviewed boost identity");
        boost["mpn"] = "REVIEWED_SHUNT_ONLY_IDENTITY_TRANSITION".into();
        anyhow::ensure!(matches.next().is_none(), "duplicate boost component");
    }
    let note = format!(" Historical geometry-only transfer {} -> {}: saved board differs only in the reviewed boost Value/MPN properties; all native geometry/net/stackup fields match. Other-device heat and cooling applicability remain unqualified.", old["board_sha256"], now["board_sha256"]);
    // Board hashes are verified above. All other fields, including extractor
    // provenance, must match; this is one reviewed transfer, not a migration API.
    for value in [&mut old, &mut now] {
        let object = value.as_object_mut().unwrap();
        for key in ["board_file_utf8", "board_sha256"] {
            object.remove(key);
        }
    }
    anyhow::ensure!(
        old == now,
        "native fields changed beyond reviewed boost identity"
    );
    Ok((retained, note))
}
