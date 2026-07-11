use crate::{error::DesignBundleError, model::DesignBundle};
use sha2::{Digest, Sha256};
pub fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn normalized_json(bundle: &DesignBundle) -> Result<String, DesignBundleError> {
    serde_json::to_string_pretty(bundle)
        .map_err(|e| DesignBundleError::Serialization(e.to_string()))
}
