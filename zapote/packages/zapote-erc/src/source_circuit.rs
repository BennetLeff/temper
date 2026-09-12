//! Compiled package-pin graph used by the gate-drive and power-entry checks.
//! A source/native match proves transport, not that the circuit intent is right.
use serde::Deserialize;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding};

#[derive(Debug, Deserialize)]
pub struct Component {
    pub instance_path: String,
    pub reference: String,
    pub mpn: String,
    pub value: Option<String>,
    pub footprint: String,
}

#[derive(Deserialize)]
struct Manifest {
    entry: String,
    components: Vec<Component>,
    bridge: Bridge,
    source_attributes: BTreeMap<String, Value>,
    footprint_census: BTreeMap<String, FootprintCensus>,
}
#[derive(Deserialize)]
struct FootprintCensus {
    pads: Vec<String>,
}
#[derive(Deserialize)]
struct Bridge {
    nets: Vec<Net>,
    components: Vec<BridgeComponent>,
}
#[derive(Deserialize)]
struct BridgeComponent {
    reference: String,
    footprint: String,
}
#[derive(Deserialize)]
struct Net {
    name: String,
    nodes: Vec<[String; 2]>,
}

#[derive(Debug)]
pub struct Circuit {
    pub components: BTreeMap<String, Component>,
    pub pins: BTreeMap<String, String>,
    pub physical_multiplicity: BTreeMap<String, usize>,
}

fn insert<K: Ord + std::fmt::Debug, V>(
    map: &mut BTreeMap<K, V>,
    key: K,
    value: V,
) -> Result<(), String> {
    if map.contains_key(&key) {
        return Err(format!("duplicate identity {key:?}"));
    }
    map.insert(key, value);
    Ok(())
}

impl Circuit {
    /// Decode physical pin numbers from the compiler bridge, rejecting omissions
    /// and duplicate identities before any device model can use the graph.
    pub fn parse(source: &str, entry: &str) -> Result<Self, String> {
        let manifest: Manifest = serde_json::from_str(source).map_err(|e| e.to_string())?;
        if manifest.entry != entry
            || manifest.components.is_empty()
            || manifest.bridge.nets.is_empty()
        {
            return Err("wrong entry or empty compiled circuit".into());
        }
        let mut refs = BTreeMap::new();
        let mut components = BTreeMap::new();
        for c in manifest.components {
            if [&c.instance_path, &c.reference, &c.mpn]
                .iter()
                .any(|s| s.trim().is_empty())
            {
                return Err("empty source component identity/value".into());
            }
            let attr = manifest
                .source_attributes
                .get(&c.instance_path)
                .ok_or("missing source attributes")?;
            if attr["mpn"] != c.mpn || attr["value"].as_str() != c.value.as_deref() {
                return Err(format!("unbound source attributes for {}", c.instance_path));
            }
            insert(&mut refs, c.reference.clone(), c.instance_path.clone())?;
            insert(&mut components, c.instance_path.clone(), c)?;
        }
        let mut names = BTreeSet::new();
        let mut pins = BTreeMap::new();
        for n in manifest.bridge.nets {
            if n.name.trim().is_empty() || n.nodes.is_empty() || !names.insert(n.name.clone()) {
                return Err("empty or repeated source net".into());
            }
            for [reference, pin] in n.nodes {
                let id = refs
                    .get(&reference)
                    .ok_or("net references unknown component")?;
                if pin.trim().is_empty() {
                    return Err("empty pin number".into());
                }
                let endpoint = format!("{id}.{pin}");
                insert(&mut pins, endpoint.clone(), n.name.clone())?;
            }
        }
        for id in components.keys() {
            if !pins.keys().any(|p| p.starts_with(&format!("{id}."))) {
                return Err(format!("component {id} has no compiled pins"));
            }
        }
        let mut footprints = BTreeMap::new();
        for c in manifest.bridge.components {
            insert(&mut footprints, c.reference, c.footprint)?;
        }
        if footprints.keys().collect::<BTreeSet<_>>() != refs.keys().collect() {
            return Err("compiler footprint/component census differs".into());
        }
        let mut physical_multiplicity = BTreeMap::new();
        for (id, component) in &components {
            let nickname = &footprints[&component.reference];
            let source_nickname = if component.footprint.contains(':') {
                component.footprint.clone()
            } else {
                format!("lib:{}", component.footprint)
            };
            if nickname != &source_nickname {
                return Err(format!("compiler footprint differs at {id}"));
            }
            let census = manifest
                .footprint_census
                .get(nickname)
                .ok_or("missing footprint census")?;
            for pin in &census.pads {
                let endpoint = format!("{id}.{pin}");
                if !pins.contains_key(&endpoint) {
                    return Err(format!("footprint pad {endpoint} has no compiled net"));
                }
                *physical_multiplicity.entry(endpoint).or_default() += 1;
            }
        }
        if pins.keys().collect::<BTreeSet<_>>() != physical_multiplicity.keys().collect() {
            return Err("source pin and physical pad census differ".into());
        }
        Ok(Self {
            components,
            pins,
            physical_multiplicity,
        })
    }

    pub fn net(&self, endpoint: &str) -> Result<&str, String> {
        self.pins
            .get(endpoint)
            .map(String::as_str)
            .ok_or_else(|| format!("missing physical pin {endpoint}"))
    }

    pub fn require_net(&self, endpoints: &[&str]) -> Result<(), String> {
        let first = endpoints.first().ok_or("empty net requirement")?;
        let expected = self.net(first)?;
        for endpoint in endpoints {
            if self.net(endpoint)? != expected {
                return Err(format!("{endpoint} is not on {first}'s net"));
            }
        }
        Ok(())
    }

    pub fn require_distinct(&self, endpoints: &[&str]) -> Result<(), String> {
        let mut nets = BTreeSet::new();
        for endpoint in endpoints {
            if !nets.insert(self.net(endpoint)?) {
                return Err(format!("independent domains/signals shorted at {endpoint}"));
            }
        }
        Ok(())
    }

    /// Bind the whole compiled graph to exported pads and connection records.
    /// The caller also runs the saved-board byte binding and native DRC gates.
    pub fn bind_native(&self, native: &str) -> Result<(), String> {
        #[derive(Deserialize)]
        struct Native {
            components: Vec<NativeComponent>,
            connections: Vec<Connection>,
        }
        #[derive(Deserialize)]
        struct NativeComponent {
            id: String,
            mpn: String,
            footprint_pads: Vec<Pad>,
        }
        #[derive(Deserialize)]
        struct Pad {
            pad: String,
            net: String,
            #[serde(default)]
            pad_type: Option<String>,
            #[serde(default)]
            uuid: Option<String>,
        }
        #[derive(Deserialize)]
        struct Connection {
            component: String,
            pin: String,
            net: String,
        }
        let n: Native = serde_json::from_str(native).map_err(|e| e.to_string())?;
        let mut ids = BTreeSet::new();
        let mut uuids = BTreeSet::new();
        let mut physical = BTreeMap::<String, (String, usize)>::new();
        for c in n.components {
            if !ids.insert(c.id.clone()) {
                return Err("duplicate native component".into());
            }
            let source = self
                .components
                .get(&c.id)
                .ok_or("unexpected native component")?;
            if source.mpn != c.mpn {
                return Err(format!("native MPN differs at {}", c.id));
            }
            for p in c.footprint_pads {
                if p.pad.is_empty()
                    && p.net.is_empty()
                    && p.pad_type.as_deref() == Some("np_thru_hole")
                {
                    let uuid = p.uuid.ok_or("mechanical hole requires UUID")?;
                    if uuid.trim().is_empty() || !uuids.insert(uuid) {
                        return Err("duplicate mechanical UUID".into());
                    }
                    continue; // Physical hole census is checked by native document binding.
                }
                let endpoint = format!("{}.{}", c.id, p.pad);
                let expected_count = self
                    .physical_multiplicity
                    .get(&endpoint)
                    .ok_or("unexpected native pad")?;
                match p.uuid {
                    Some(uuid) if uuid.trim().is_empty() || !uuids.insert(uuid.clone()) => {
                        return Err("empty or duplicate native pad UUID".into())
                    }
                    None if *expected_count > 1 => {
                        return Err("every repeated physical pad requires its own UUID".into())
                    }
                    _ => {}
                }
                let entry = physical.entry(endpoint).or_insert((p.net.clone(), 0));
                if entry.0 != p.net {
                    return Err("physical duplicate pads have conflicting nets".into());
                }
                entry.1 += 1;
            }
        }
        let mut connections = BTreeMap::<String, (String, usize)>::new();
        for c in n.connections {
            let endpoint = format!("{}.{}", c.component, c.pin);
            let entry = connections.entry(endpoint).or_insert((c.net.clone(), 0));
            if entry.0 != c.net {
                return Err("logical duplicate connections have conflicting nets".into());
            }
            entry.1 += 1;
        }
        let expected: BTreeMap<_, _> = self
            .physical_multiplicity
            .iter()
            .map(|(k, count)| (k.clone(), (self.pins[k].clone(), *count)))
            .collect();
        if ids != self.components.keys().cloned().collect()
            || physical != expected
            || connections != expected
        {
            return Err(
                "compiled component/pin census differs from native pads/connections".into(),
            );
        }
        Ok(())
    }
}

pub fn validate(source: &str, native: &str, entry: &str) -> CheckReport {
    let result = Circuit::parse(source, entry).and_then(|c| c.bind_native(native));
    let rule = "ERC.SOURCE.NATIVE_GRAPH_BINDING";
    let finding = match result {
        Ok(()) => Finding::pass(
            rule,
            "complete compiler graph matches native package pins and MPNs",
            entry,
        ),
        Err(e) => Finding::fail(rule, e, entry),
    };
    CheckReport::from_findings(vec![finding], vec![rule.into()], vec![])
}
