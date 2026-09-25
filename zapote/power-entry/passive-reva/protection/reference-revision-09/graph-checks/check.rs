//! Standalone structural checker for the generated KiCad netlist.
//!
//! This is deliberately dependency-free: compile it with `rustc`, point it at
//! a generated `default.net`, and it checks selected compiled endpoint constraints
//! that the source-candidate integration promises.  It does not qualify a
//! PCB, solve placement, or infer electrical behavior from names alone.

use std::collections::{HashMap, HashSet};
use std::env;
use std::fmt;
use std::fs;
use std::path::Path;

const EXPECTED_COMPONENTS: usize = 131;

#[derive(Debug, Clone, PartialEq, Eq)]
enum Token {
    LParen,
    RParen,
    Atom(String),
    String(String),
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum SExpr {
    Atom(String),
    List(Vec<SExpr>),
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct Node {
    reference: String,
    pin: String,
}

#[derive(Debug, Clone)]
struct Component {
    reference: String,
    instance_path: String,
}

#[derive(Debug, Clone)]
struct Net {
    name: String,
    nodes: Vec<Node>,
}

#[derive(Debug, Clone)]
struct Graph {
    components: HashMap<String, Component>,
    nets: Vec<Net>,
    by_node: HashMap<(String, String), String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct GraphError(String);

impl fmt::Display for GraphError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

fn error(message: impl Into<String>) -> GraphError {
    GraphError(message.into())
}

fn tokenize(input: &str) -> Result<Vec<Token>, GraphError> {
    let bytes = input.as_bytes();
    let mut index = 0;
    let mut tokens = Vec::new();
    while index < bytes.len() {
        match bytes[index] {
            b'(' => {
                tokens.push(Token::LParen);
                index += 1;
            }
            b')' => {
                tokens.push(Token::RParen);
                index += 1;
            }
            b'"' => {
                index += 1;
                let mut value = String::new();
                let mut closed = false;
                while index < bytes.len() {
                    match bytes[index] {
                        b'"' => {
                            index += 1;
                            closed = true;
                            break;
                        }
                        b'\\' => {
                            index += 1;
                            let Some(&escaped) = bytes.get(index) else {
                                return Err(error("unterminated escape in quoted string"));
                            };
                            match escaped {
                                b'n' => value.push('\n'),
                                b'r' => value.push('\r'),
                                b't' => value.push('\t'),
                                b'"' => value.push('"'),
                                b'\\' => value.push('\\'),
                                other => value.push(other as char),
                            }
                            index += 1;
                        }
                        byte => {
                            value.push(byte as char);
                            index += 1;
                        }
                    }
                }
                if !closed {
                    return Err(error("unterminated quoted string"));
                }
                tokens.push(Token::String(value));
            }
            byte if byte.is_ascii_whitespace() => index += 1,
            b';' => {
                // KiCad exports do not normally contain comments, but accepting
                // line comments keeps this parser strict about forms while being
                // tolerant of hand-edited fixtures.
                while index < bytes.len() && bytes[index] != b'\n' {
                    index += 1;
                }
            }
            _ => {
                let start = index;
                while index < bytes.len()
                    && !bytes[index].is_ascii_whitespace()
                    && bytes[index] != b'('
                    && bytes[index] != b')'
                    && bytes[index] != b';'
                {
                    index += 1;
                }
                if start == index {
                    return Err(error("empty atom"));
                }
                let atom = std::str::from_utf8(&bytes[start..index])
                    .map_err(|_| error("netlist contains non-UTF-8 atom"))?;
                tokens.push(Token::Atom(atom.to_owned()));
            }
        }
    }
    Ok(tokens)
}

fn parse_list(tokens: &[Token], cursor: &mut usize) -> Result<SExpr, GraphError> {
    if !matches!(tokens.get(*cursor), Some(Token::LParen)) {
        return Err(error("expected opening parenthesis"));
    }
    *cursor += 1;
    let mut children = Vec::new();
    loop {
        match tokens.get(*cursor) {
            Some(Token::RParen) => {
                *cursor += 1;
                return Ok(SExpr::List(children));
            }
            Some(Token::LParen) => children.push(parse_list(tokens, cursor)?),
            Some(Token::Atom(atom)) => {
                children.push(SExpr::Atom(atom.clone()));
                *cursor += 1;
            }
            Some(Token::String(value)) => {
                children.push(SExpr::Atom(value.clone()));
                *cursor += 1;
            }
            None => {
                return Err(error(
                    "unbalanced S-expression: missing closing parenthesis",
                ))
            }
        }
    }
}

fn parse(input: &str) -> Result<SExpr, GraphError> {
    let tokens = tokenize(input)?;
    let mut cursor = 0;
    let root = parse_list(&tokens, &mut cursor)?;
    if cursor != tokens.len() {
        return Err(error("trailing tokens after root S-expression"));
    }
    Ok(root)
}

fn atom(node: &SExpr) -> Result<&str, GraphError> {
    match node {
        SExpr::Atom(value) => Ok(value),
        SExpr::List(_) => Err(error("expected atom")),
    }
}

fn list(node: &SExpr) -> Result<&[SExpr], GraphError> {
    match node {
        SExpr::List(children) => Ok(children),
        SExpr::Atom(_) => Err(error("expected list")),
    }
}

fn head(node: &SExpr) -> Result<&str, GraphError> {
    let first = list(node)?.first().ok_or_else(|| error("empty list"))?;
    atom(first)
}

fn field_value(node: &SExpr) -> Result<&str, GraphError> {
    let fields = list(node)?;
    if fields.len() != 2 {
        return Err(error("expected a two-item field"));
    }
    atom(&fields[1])
}

fn child_field<'a>(node: &'a SExpr, name: &str) -> Option<&'a SExpr> {
    list(node)
        .ok()?
        .iter()
        .skip(1)
        .find(|child| head(child).ok() == Some(name))
}

fn suffix_instance_path(names: &str) -> Result<String, GraphError> {
    let Some((_, suffix)) = names.rsplit_once("::") else {
        return Err(error(format!(
            "sheetpath names lacks :: instance suffix: {names}"
        )));
    };
    if suffix.is_empty() || suffix.contains('/') {
        return Err(error(format!("invalid instance suffix: {suffix}")));
    }
    Ok(suffix.to_owned())
}

fn parse_graph(input: &str) -> Result<Graph, GraphError> {
    let root = parse(input)?;
    let root_fields = list(&root)?;
    if root_fields.first().and_then(|n| atom(n).ok()) != Some("export") {
        return Err(error("root form is not (export ...)"));
    }
    let components_form = root_fields
        .iter()
        .find(|node| head(node).ok() == Some("components"))
        .ok_or_else(|| error("missing components form"))?;
    let nets_form = root_fields
        .iter()
        .find(|node| head(node).ok() == Some("nets"))
        .ok_or_else(|| error("missing nets form"))?;

    let mut components = HashMap::new();
    let mut instance_paths = HashSet::new();
    for comp_form in list(components_form)?.iter().skip(1) {
        if head(comp_form)? != "comp" {
            return Err(error("unexpected form under components"));
        }
        let reference = child_field(comp_form, "ref")
            .ok_or_else(|| error("component missing ref"))
            .and_then(field_value)?
            .to_owned();
        if components.contains_key(&reference) {
            return Err(error(format!("duplicate component ref {reference}")));
        }
        let sheetpath = child_field(comp_form, "sheetpath")
            .ok_or_else(|| error(format!("{reference} missing sheetpath")))?;
        let names = child_field(sheetpath, "names")
            .ok_or_else(|| error(format!("{reference} missing sheetpath names")))
            .and_then(field_value)?;
        let instance_path = suffix_instance_path(names)?;
        if !instance_paths.insert(instance_path.clone()) {
            return Err(error(format!(
                "duplicate component instance path {instance_path}"
            )));
        }
        components.insert(
            reference.clone(),
            Component {
                reference,
                instance_path,
            },
        );
    }
    if components.len() != EXPECTED_COMPONENTS {
        return Err(error(format!(
            "component count {} != expected {EXPECTED_COMPONENTS}",
            components.len()
        )));
    }

    let mut nets = Vec::new();
    let mut net_codes = HashSet::new();
    let mut net_names = HashSet::new();
    let mut by_node = HashMap::new();
    for net_form in list(nets_form)?.iter().skip(1) {
        if head(net_form)? != "net" {
            return Err(error("unexpected form under nets"));
        }
        let code = child_field(net_form, "code")
            .ok_or_else(|| error("net missing code"))
            .and_then(field_value)?
            .to_owned();
        let name = child_field(net_form, "name")
            .ok_or_else(|| error(format!("net {code} missing name")))
            .and_then(field_value)?
            .to_owned();
        if !net_codes.insert(code.clone()) {
            return Err(error(format!("duplicate net code {code}")));
        }
        if !net_names.insert(name.clone()) {
            return Err(error(format!("duplicate net name {name}")));
        }
        let mut nodes = Vec::new();
        let mut local_nodes = HashSet::new();
        for node_form in list(net_form)?.iter().skip(1) {
            if head(node_form)? != "node" {
                continue;
            }
            let reference = child_field(node_form, "ref")
                .ok_or_else(|| error(format!("net {name} node missing ref")))
                .and_then(field_value)?
                .to_owned();
            let pin = child_field(node_form, "pin")
                .ok_or_else(|| error(format!("net {name} node {reference} missing pin")))
                .and_then(field_value)?
                .to_owned();
            if !components.contains_key(&reference) {
                return Err(error(format!(
                    "net {name} references unknown component {reference}"
                )));
            }
            let key = (reference.clone(), pin.clone());
            if !local_nodes.insert(key.clone()) {
                return Err(error(format!(
                    "duplicate pin {reference}.{pin} on net {name}"
                )));
            }
            if by_node.insert(key, name.clone()).is_some() {
                return Err(error(format!(
                    "pin {reference}.{pin} appears on multiple nets"
                )));
            }
            nodes.push(Node { reference, pin });
        }
        nets.push(Net { name, nodes });
    }
    Ok(Graph {
        components,
        nets,
        by_node,
    })
}

impl Graph {
    fn net_for(&self, reference: &str, pin: &str) -> Result<&str, GraphError> {
        self.by_node
            .get(&(reference.to_owned(), pin.to_owned()))
            .map(String::as_str)
            .ok_or_else(|| error(format!("missing endpoint {reference}.{pin}")))
    }

    fn nodes_on(&self, net: &str) -> Vec<(&str, &str)> {
        self.nets
            .iter()
            .find(|candidate| candidate.name == net)
            .map(|candidate| {
                candidate
                    .nodes
                    .iter()
                    .map(|node| (node.reference.as_str(), node.pin.as_str()))
                    .collect()
            })
            .unwrap_or_default()
    }

    fn assert_same_net(&self, endpoints: &[(&str, &str)], label: &str) -> Result<(), GraphError> {
        let Some(&(reference, pin)) = endpoints.first() else {
            return Err(error(format!("{label}: no endpoints")));
        };
        let expected = self.net_for(reference, pin)?;
        for &(other_reference, other_pin) in endpoints.iter().skip(1) {
            let actual = self.net_for(other_reference, other_pin)?;
            if actual != expected {
                return Err(error(format!(
                    "{label}: {reference}.{pin} is on {expected}, {other_reference}.{other_pin} is on {actual}"
                )));
            }
        }
        Ok(())
    }

    fn assert_different_net(
        &self,
        left: (&str, &str),
        right: (&str, &str),
        label: &str,
    ) -> Result<(), GraphError> {
        let left_net = self.net_for(left.0, left.1)?;
        let right_net = self.net_for(right.0, right.1)?;
        if left_net == right_net {
            return Err(error(format!("{label}: both endpoints are on {left_net}")));
        }
        Ok(())
    }

    fn component_path(&self, path: &str) -> Result<&Component, GraphError> {
        self.components
            .values()
            .find(|component| component.instance_path == path)
            .ok_or_else(|| error(format!("missing component instance {path}")))
    }

    fn role_ref(&self, path: &str) -> Result<&str, GraphError> {
        Ok(self.component_path(path)?.reference.as_str())
    }

    fn check(&self) -> Result<(), GraphError> {
        let clamp = self.component_path("isense_clamp")?;
        let clamp_ref = clamp.reference.as_str();
        let pfc_ref = self.role_ref("pfc")?;
        let r_isense_ref = self.role_ref("r_isense")?;
        let c_isense_ref = self.role_ref("c_isense")?;
        self.assert_same_net(
            &[(clamp_ref, "1"), (pfc_ref, "1")],
            "isense clamp pin 1 is controller ground",
        )?;
        self.assert_same_net(
            &[
                (clamp_ref, "3"),
                (pfc_ref, "3"),
                (r_isense_ref, "1"),
                (c_isense_ref, "1"),
            ],
            "isense clamp pin 3 is filtered ISENSE",
        )?;
        let clamp_pin2_net = self.net_for(clamp_ref, "2")?;
        if self.nodes_on(clamp_pin2_net).len() != 1 {
            return Err(error(format!(
                "isense clamp pin 2 is not singleton on {clamp_pin2_net}"
            )));
        }

        let shunt_ref = self.role_ref("shunt")?;
        let bridge_ref = self.role_ref("bridge")?;
        self.assert_same_net(
            &[(shunt_ref, "2"), (r_isense_ref, "2"), (bridge_ref, "4")],
            "shunt rectifier-side return and filtered sense input",
        )?;
        self.assert_different_net(
            (shunt_ref, "2"),
            (pfc_ref, "1"),
            "shunt return must remain separate from controller ground",
        )?;
        let diode = self.component_path("d_boost")?;
        let r_vtop_ref = self.role_ref("r_vtop")?;
        let vd_r1_ref = self.role_ref("protection.vd_div.r1")?;
        let c1_ref = self.role_ref("c1")?;
        let vb_r1_ref = self.role_ref("protection.vb_div.r1")?;
        self.assert_same_net(
            &[
                (diode.reference.as_str(), "2"),
                (r_vtop_ref, "1"),
                (vd_r1_ref, "1"),
            ],
            "boost diode K/local_vd feedback",
        )?;
        self.assert_same_net(
            &[(c1_ref, "1"), (vb_r1_ref, "1")],
            "bulk positive and protection vb divider high",
        )?;
        self.assert_different_net(
            (r_vtop_ref, "1"),
            (c1_ref, "1"),
            "local_vd and bulk-bank positive must be distinct",
        )?;

        let pwm_iso_ref = self.role_ref("protection.pwm_iso")?;
        let gate_r_ref = self.role_ref("protection.gate_r")?;
        let gate_off_r_ref = self.role_ref("protection.gate_off_r")?;
        let gate_pd_ref = self.role_ref("protection.gate_pd")?;
        let q_boost_ref = self.role_ref("q_boost")?;
        let driver_ref = self.role_ref("protection.driver")?;
        self.assert_same_net(
            &[(driver_ref, "2"), (gate_r_ref, "1")],
            "gate-driver OUTH (pin 2) to gate_r input",
        )?;
        self.assert_same_net(
            &[(driver_ref, "3"), (gate_off_r_ref, "1")],
            "gate-driver OUTL (pin 3) to gate_off_r input",
        )?;
        self.assert_same_net(
            &[(pfc_ref, "8"), (pwm_iso_ref, "1")],
            "PFC GATE to isolated PWM resistor",
        )?;
        self.assert_same_net(
            &[
                (gate_r_ref, "2"),
                (gate_off_r_ref, "2"),
                (gate_pd_ref, "1"),
                (q_boost_ref, "1"),
            ],
            "protected gate resistors to MOSFET gate",
        )?;
        self.assert_different_net(
            (pfc_ref, "8"),
            (q_boost_ref, "1"),
            "PFC pin 8 must not directly touch MOSFET gate",
        )?;
        self.assert_same_net(
            &[(driver_ref, "6"), (pwm_iso_ref, "2")],
            "driver INP through pwm_iso",
        )?;
        self.assert_different_net(
            (pfc_ref, "8"),
            (driver_ref, "6"),
            "driver INP remains behind 1k isolation",
        )?;
        self.assert_same_net(
            &[(pfc_ref, "7"), (driver_ref, "1")],
            "PFC VCC and gate-driver VDD aux rail",
        )?;
        self.assert_same_net(
            &[(pfc_ref, "1"), (driver_ref, "4")],
            "PFC GND and gate-driver GND",
        )?;
        self.assert_same_net(
            &[(gate_pd_ref, "2"), (pfc_ref, "1")],
            "gate pulldown returns to controller ground",
        )?;
        self.assert_same_net(
            &[(shunt_ref, "1"), (c_isense_ref, "2"), (pfc_ref, "1")],
            "shunt ground side and ISENSE filter return to controller ground",
        )?;

        let r_permit_gate_ref = self.role_ref("r_permit_gate")?;
        let enable_and_ref = self.role_ref("protection.enable_and")?;
        let permit_ref = self.role_ref("permit")?;
        let permit_buf_ref = self.role_ref("protection.permit_buf")?;
        let arm_buf_ref = self.role_ref("protection.arm_buf")?;
        let q_permit_ref = self.role_ref("q_permit")?;
        self.assert_same_net(
            &[(r_permit_gate_ref, "1"), (enable_and_ref, "4")],
            "standby permit resistor to enable_and Y",
        )?;
        self.assert_different_net(
            (permit_ref, "1"),
            (r_permit_gate_ref, "1"),
            "external hot permit must cross permit buffer",
        )?;
        self.assert_same_net(
            &[(permit_ref, "1"), (permit_buf_ref, "2")],
            "canonical permit socket to permit_buf A",
        )?;
        self.assert_same_net(
            &[(r_permit_gate_ref, "2"), (q_permit_ref, "1")],
            "permit gate resistor to q_permit gate",
        )?;
        self.assert_different_net(
            (permit_ref, "1"),
            (enable_and_ref, "4"),
            "external permit must not bypass enable_and",
        )?;
        let arm_net = self.net_for(arm_buf_ref, "2")?;
        if self.nodes_on(arm_net).len() != 1 {
            return Err(error(format!(
                "ARM buffer input is not a dedicated singleton net: {arm_net}"
            )));
        }
        if arm_net != "hot_arm" {
            return Err(error(format!(
                "ARM buffer input lost hot_arm port net: {arm_net}"
            )));
        }
        let ref_bias_ref = self.role_ref("protection.ref_bias")?;
        let cmp_vd_ref = self.role_ref("protection.cmp_vd")?;
        let sup_logic_ref = self.role_ref("protection.sup_logic")?;
        let aux_ref = self.role_ref("aux")?;
        let control_ref = self.role_ref("control")?;
        self.assert_same_net(
            &[(ref_bias_ref, "1"), (cmp_vd_ref, "8"), (sup_logic_ref, "4")],
            "logic5 powers reference and detector",
        )?;
        let logic_net = self.net_for(ref_bias_ref, "1")?;
        if logic_net != "logic5" {
            return Err(error(format!(
                "logic5 port lost its canonical net name: {logic_net}"
            )));
        }
        if self
            .nodes_on(logic_net)
            .iter()
            .any(|(reference, _)| [aux_ref, control_ref, permit_ref].contains(reference))
        {
            return Err(error(
                "logic5 unexpectedly attached to an external connector",
            ));
        }
        Ok(())
    }
}

fn read_graph(path: &Path) -> Result<Graph, GraphError> {
    let contents =
        fs::read_to_string(path).map_err(|e| error(format!("read {}: {e}", path.display())))?;
    parse_graph(&contents)
}

fn main() {
    let path = env::args()
        .nth(1)
        .unwrap_or_else(|| "build/default.net".to_owned());
    match read_graph(Path::new(&path)).and_then(|graph| graph.check()) {
        Ok(()) => println!("PASS selected compiled connectivity checks: {path} ({EXPECTED_COMPONENTS} components; no electrical qualification performed)"),
        Err(err) => {
            eprintln!("graph proof FAIL: {err}");
            std::process::exit(1);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> String {
        let path = env::var("GRAPH_FIXTURE").unwrap_or_else(|_| {
            "/private/tmp/temper-pkgs-1-4/zapote/power-entry/passive-reva/protection/reference-revision-09/source-candidate/build/default.net".to_owned()
        });
        fs::read_to_string(path).expect("fixture must be available")
    }

    fn valid_fixture() -> String {
        let input = fixture();
        let graph = parse_graph(&input).expect("fixture parses");
        graph.check().expect("fixture connectivity proof");
        input
    }

    fn role_ref(input: &str, path: &str) -> String {
        parse_graph(input)
            .expect("fixture parses")
            .component_path(path)
            .expect("fixture role exists")
            .reference
            .clone()
    }

    fn node(reference: &str, pin: &str) -> String {
        format!("(node (ref \"{reference}\") (pin \"{pin}\")")
    }

    fn mutate(input: &str, from: &str, to: &str) -> String {
        let Some(index) = input.find(from) else {
            panic!("mutation needle not found: {from}");
        };
        let mut output = input.to_owned();
        output.replace_range(index..index + from.len(), to);
        output
    }

    fn swap_all(input: &str, left: &str, right: &str) -> String {
        let marker = "__GRAPH_CHECK_SWAP__";
        assert!(input.contains(left), "swap needle not found: {left}");
        assert!(input.contains(right), "swap needle not found: {right}");
        input
            .replace(left, marker)
            .replace(right, left)
            .replace(marker, right)
    }

    #[test]
    fn candidate_fixture_proves_expected_graph() {
        let _ = valid_fixture();
    }

    #[test]
    fn parser_rejects_unbalanced_sexpr() {
        let input = fixture();
        let truncated = input.trim_end().trim_end_matches(')').to_owned();
        assert!(parse_graph(&truncated).is_err());
    }

    #[test]
    fn checker_rejects_reversed_clamp_pins() {
        let base = valid_fixture();
        let clamp = role_ref(&base, "isense_clamp");
        let input = swap_all(&base, &node(&clamp, "1"), &node(&clamp, "3"));
        let graph = parse_graph(&input).expect("pin swap remains a well-formed graph");
        assert!(graph.check().is_err());
    }

    #[test]
    fn checker_rejects_feedback_tied_to_bulk_bank() {
        let base = valid_fixture();
        let r_vtop = role_ref(&base, "r_vtop");
        let c1 = role_ref(&base, "c1");
        let input = swap_all(&base, &node(&r_vtop, "1"), &node(&c1, "1"));
        let graph = parse_graph(&input).expect("feedback/bulk swap remains a well-formed graph");
        assert!(graph.check().is_err());
    }

    #[test]
    fn checker_rejects_direct_gate_bypass() {
        let base = valid_fixture();
        let pwm_iso = role_ref(&base, "protection.pwm_iso");
        let q_boost = role_ref(&base, "q_boost");
        let input = swap_all(&base, &node(&pwm_iso, "1"), &node(&q_boost, "1"));
        let graph = parse_graph(&input).expect("gate bypass swap remains a well-formed graph");
        assert!(graph.check().is_err());
    }

    #[test]
    fn checker_rejects_standby_external_bypass() {
        let base = valid_fixture();
        let r_permit_gate = role_ref(&base, "r_permit_gate");
        let permit = role_ref(&base, "permit");
        let input = swap_all(&base, &node(&r_permit_gate, "1"), &node(&permit, "1"));
        let graph = parse_graph(&input).expect("permit bypass swap remains a well-formed graph");
        assert!(graph.check().is_err());
    }

    #[test]
    fn parser_rejects_missing_endpoint() {
        let base = fixture();
        let clamp = role_ref(&base, "isense_clamp");
        let input = mutate(&base, &node(&clamp, "2"), &node("U999", "2"));
        assert!(parse_graph(&input).is_err());
    }

    #[test]
    fn parser_rejects_duplicate_component_ref() {
        let base = fixture();
        let r1 = role_ref(&base, "protection.vd_div.r1");
        let r2 = role_ref(&base, "protection.vd_div.r2");
        let input = mutate(
            &base,
            &format!("(comp (ref \"{r1}\")"),
            &format!("(comp (ref \"{r2}\")"),
        );
        assert!(parse_graph(&input).is_err());
    }

    #[test]
    fn parser_rejects_duplicate_pin_endpoint() {
        let base = fixture();
        let r_vtop = role_ref(&base, "r_vtop");
        let c1 = role_ref(&base, "c1");
        let input = mutate(&base, &node(&r_vtop, "1"), &node(&c1, "1"));
        assert!(parse_graph(&input).is_err());
    }
}
