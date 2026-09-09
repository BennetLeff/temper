//! Only operator-reviewed, pinned receipts may qualify external engineering evidence.
use serde_json::Value;
use sha2::{Digest, Sha256};

pub fn approved(kind: &str, receipt: &Value) -> bool {
    let registry: Value =
        serde_json::from_str(include_str!("../engineering/approved-evidence.json"))
            .expect("embedded approval registry must be valid JSON");
    approved_by(&registry, kind, receipt)
}

fn approved_by(registry: &Value, kind: &str, receipt: &Value) -> bool {
    let Some(id) = receipt["id"].as_str().filter(|id| !id.is_empty()) else {
        return false;
    };
    if receipt["synthetic"] != false
        || receipt["status"] != "pass"
        || receipt["reviewed_by"].as_str().is_none_or(str::is_empty)
    {
        return false;
    }
    let mut canonical = receipt.clone();
    if let Some(object) = canonical.as_object_mut() {
        object.remove("verified_artifact");
    }
    let digest = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&canonical).expect("JSON receipt"))
    );
    registry[kind][id].as_str() == Some(digest.as_str())
}

pub fn evaluate(input: Value) -> anyhow::Result<Value> {
    anyhow::ensure!(
        input["profile"] == "engineering-qualification",
        "qualification profile required"
    );
    let kind = input["kind"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("qualification kind required"))?;
    Ok(serde_json::json!({"status":if approved(kind,&input["receipt"]){"pass"}else{"blocked"}}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn only_exact_reviewed_receipt_is_admitted() {
        let q = json!({"id":"control","status":"pass","synthetic":false,"reviewed_by":"test","source":"software control","value":1.0});
        let hash = format!("{:x}", Sha256::digest(serde_json::to_vec(&q).unwrap()));
        let registry = json!({"component":{"control":hash}});
        assert!(approved_by(&registry, "component", &q));
        assert!(!approved("component", &q));
        for (key, value) in [
            ("synthetic", json!(true)),
            ("status", json!("blocked")),
            ("value", json!(2.0)),
            ("reviewed_by", json!("")),
        ] {
            let mut bad = q.clone();
            bad[key] = value;
            assert!(!approved_by(&registry, "component", &bad));
        }
    }
}
