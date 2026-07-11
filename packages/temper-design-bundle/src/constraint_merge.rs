use crate::{
    error::{DesignBundleError, diagnostic},
    model::{Constraint, ConstraintOrigin, ConstraintSet},
};
use std::collections::BTreeMap;
pub fn merge(
    derived: Vec<Constraint>,
    authored: Vec<Constraint>,
) -> Result<ConstraintSet, DesignBundleError> {
    let mut out = BTreeMap::<String, Constraint>::new();
    for c in derived {
        out.insert(key(&c), c);
    }
    for c in authored {
        let k = key(&c);
        if let Some(existing) = out.get(&k) {
            if c.value_mm < existing.value_mm && existing.origin == ConstraintOrigin::AtopileDerived
            {
                return Err(diagnostic(
                    "safety_weakening",
                    format!(
                        "{} weakens {} from {} mm to {} mm",
                        c.id, existing.id, existing.value_mm, c.value_mm
                    ),
                    vec![existing.id.clone(), c.id.clone()],
                ));
            }
            if c.value_mm == existing.value_mm {
                continue;
            }
            if c.value_mm > existing.value_mm {
                out.insert(k, c);
            }
        } else {
            out.insert(k, c);
        }
    }
    Ok(ConstraintSet {
        constraints: out.into_values().collect(),
    })
}

fn key(c: &Constraint) -> String {
    format!("{}\u{1f}{}", c.subject, c.metric)
}
