//! Reject incomplete catch geometry before a misleading field solve.
//!
//! The previous gate matched substrings, so `{"status":
//! "COMPLETE_PHYSICAL_FIELD_GEOMETRY", "segments": []}` authorised a solve
//! (round-6 investigation, installed-model.md). This version parses the file
//! and authorises only a structurally complete, provenance-checked, closed
//! current path. Contract (all required):
//!
//! ```json
//! {"status": "COMPLETE_PHYSICAL_FIELD_GEOMETRY",
//!  "segments": [{"id": "s1", "kind": "fuse_holder_path",
//!                "from": "n1", "to": "n2",
//!                "provenance": {"class": "physical", "source": "path/rel/to/root",
//!                               "sha256": "<64 hex>"}}, ...]}
//! ```
//!
//! - `status` is exactly COMPLETE_PHYSICAL_FIELD_GEOMETRY (case-sensitive);
//! - `segments` is non-empty; every segment has string `id` (unique), `kind`,
//!   `from`, `to` (from != to) and a `provenance` object;
//! - every kind in REQUIRED_KINDS is present (the four paths the old gate's
//!   reason names);
//! - `provenance.class` is `physical` or `bounded_model`; `source` is a
//!   relative path under the root given as the second argument; the file
//!   exists and its SHA-256 equals `provenance.sha256`;
//! - the segments form one closed loop: one connected graph in which every
//!   node has degree exactly 2;
//! - no string anywhere contains UNKNOWN, APPROXIMATION, UNRESOLVED or
//!   PORT_CLOSURE_ONLY (case-insensitive).
//!
//!     geometry_gate <topology.json> [<root>]     (root defaults to ".")
//! Exit 0 and field_solve_authorized=true only if every check passes; exit 3
//! otherwise, listing every failed check.
use std::collections::{BTreeMap, BTreeSet};
use std::{env, fs, path::Path, process};

const STATUS: &str = "COMPLETE_PHYSICAL_FIELD_GEOMETRY";
const REQUIRED_KINDS: [&str; 4] =
    ["fuse_holder_path", "catch_diode_die_bond", "catch_capacitor_distribution", "native_return_closure"];
const FORBIDDEN: [&str; 4] = ["UNKNOWN", "APPROXIMATION", "UNRESOLVED", "PORT_CLOSURE_ONLY"];
const CLASSES: [&str; 2] = ["physical", "bounded_model"];

// ---------------------------------------------------------------- JSON

#[derive(Debug, Clone, PartialEq)]
enum J {
    Null,
    Bool(bool),
    Num(f64),
    Str(String),
    Arr(Vec<J>),
    Obj(BTreeMap<String, J>),
}

struct P<'a> {
    s: &'a [u8],
    i: usize,
}

impl<'a> P<'a> {
    fn ws(&mut self) {
        while self.i < self.s.len() && (self.s[self.i] as char).is_ascii_whitespace() {
            self.i += 1;
        }
    }
    fn eat(&mut self, c: u8) -> Result<(), String> {
        self.ws();
        if self.s.get(self.i) == Some(&c) {
            self.i += 1;
            Ok(())
        } else {
            Err(format!("expected '{}' at byte {}", c as char, self.i))
        }
    }
    fn val(&mut self) -> Result<J, String> {
        self.ws();
        match self.s.get(self.i) {
            Some(b'{') => {
                self.i += 1;
                let mut m = BTreeMap::new();
                self.ws();
                if self.s.get(self.i) == Some(&b'}') {
                    self.i += 1;
                    return Ok(J::Obj(m));
                }
                loop {
                    self.ws();
                    let k = match self.val()? {
                        J::Str(k) => k,
                        _ => return Err(format!("object key not a string at byte {}", self.i)),
                    };
                    self.eat(b':')?;
                    let v = self.val()?;
                    if m.insert(k.clone(), v).is_some() {
                        return Err(format!("duplicate key {k:?}"));
                    }
                    self.ws();
                    match self.s.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b'}') => {
                            self.i += 1;
                            return Ok(J::Obj(m));
                        }
                        _ => return Err(format!("expected ',' or '}}' at byte {}", self.i)),
                    }
                }
            }
            Some(b'[') => {
                self.i += 1;
                let mut v = Vec::new();
                self.ws();
                if self.s.get(self.i) == Some(&b']') {
                    self.i += 1;
                    return Ok(J::Arr(v));
                }
                loop {
                    v.push(self.val()?);
                    self.ws();
                    match self.s.get(self.i) {
                        Some(b',') => self.i += 1,
                        Some(b']') => {
                            self.i += 1;
                            return Ok(J::Arr(v));
                        }
                        _ => return Err(format!("expected ',' or ']' at byte {}", self.i)),
                    }
                }
            }
            Some(b'"') => {
                self.i += 1;
                let mut out = String::new();
                loop {
                    match self.s.get(self.i) {
                        None => return Err("unterminated string".into()),
                        Some(b'"') => {
                            self.i += 1;
                            return Ok(J::Str(out));
                        }
                        Some(b'\\') => {
                            let e = *self.s.get(self.i + 1).ok_or("bad escape")?;
                            self.i += 2;
                            match e {
                                b'"' => out.push('"'),
                                b'\\' => out.push('\\'),
                                b'/' => out.push('/'),
                                b'n' => out.push('\n'),
                                b't' => out.push('\t'),
                                b'r' => out.push('\r'),
                                b'b' => out.push('\u{8}'),
                                b'f' => out.push('\u{c}'),
                                b'u' => {
                                    let h = std::str::from_utf8(self.s.get(self.i..self.i + 4).ok_or("bad \\u")?)
                                        .map_err(|_| "bad \\u")?;
                                    let c = u32::from_str_radix(h, 16).map_err(|_| "bad \\u")?;
                                    out.push(char::from_u32(c).unwrap_or('\u{fffd}'));
                                    self.i += 4;
                                }
                                _ => return Err("bad escape".into()),
                            }
                        }
                        Some(_) => {
                            let start = self.i;
                            while self.i < self.s.len() && self.s[self.i] != b'"' && self.s[self.i] != b'\\' {
                                self.i += 1;
                            }
                            out.push_str(std::str::from_utf8(&self.s[start..self.i]).map_err(|_| "invalid utf-8")?);
                        }
                    }
                }
            }
            Some(b't') if self.s[self.i..].starts_with(b"true") => {
                self.i += 4;
                Ok(J::Bool(true))
            }
            Some(b'f') if self.s[self.i..].starts_with(b"false") => {
                self.i += 5;
                Ok(J::Bool(false))
            }
            Some(b'n') if self.s[self.i..].starts_with(b"null") => {
                self.i += 4;
                Ok(J::Null)
            }
            Some(c) if *c == b'-' || c.is_ascii_digit() => {
                let start = self.i;
                while self.i < self.s.len() && b"+-.eE0123456789".contains(&self.s[self.i]) {
                    self.i += 1;
                }
                let t = std::str::from_utf8(&self.s[start..self.i]).unwrap();
                t.parse().map(J::Num).map_err(|_| format!("bad number {t:?}"))
            }
            _ => Err(format!("unexpected input at byte {}", self.i)),
        }
    }
}

fn parse(text: &str) -> Result<J, String> {
    let mut p = P { s: text.as_bytes(), i: 0 };
    let v = p.val()?;
    p.ws();
    if p.i != p.s.len() {
        return Err(format!("trailing data at byte {}", p.i));
    }
    Ok(v)
}

// ---------------------------------------------------------------- SHA-256

fn sha256(data: &[u8]) -> String {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98,
        0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
        0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8,
        0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
        0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
        0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7,
        0xc67178f2,
    ];
    let mut h: [u32; 8] =
        [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    let mut m = data.to_vec();
    let bits = (data.len() as u64).wrapping_mul(8);
    m.push(0x80);
    while m.len() % 64 != 56 {
        m.push(0);
    }
    m.extend_from_slice(&bits.to_be_bytes());
    for chunk in m.chunks(64) {
        let mut w = [0u32; 64];
        for t in 0..16 {
            w[t] = u32::from_be_bytes([chunk[4 * t], chunk[4 * t + 1], chunk[4 * t + 2], chunk[4 * t + 3]]);
        }
        for t in 16..64 {
            let s0 = w[t - 15].rotate_right(7) ^ w[t - 15].rotate_right(18) ^ (w[t - 15] >> 3);
            let s1 = w[t - 2].rotate_right(17) ^ w[t - 2].rotate_right(19) ^ (w[t - 2] >> 10);
            w[t] = w[t - 16].wrapping_add(s0).wrapping_add(w[t - 7]).wrapping_add(s1);
        }
        let mut v = h;
        for t in 0..64 {
            let s1 = v[4].rotate_right(6) ^ v[4].rotate_right(11) ^ v[4].rotate_right(25);
            let ch = (v[4] & v[5]) ^ (!v[4] & v[6]);
            let t1 = v[7].wrapping_add(s1).wrapping_add(ch).wrapping_add(K[t]).wrapping_add(w[t]);
            let s0 = v[0].rotate_right(2) ^ v[0].rotate_right(13) ^ v[0].rotate_right(22);
            let maj = (v[0] & v[1]) ^ (v[0] & v[2]) ^ (v[1] & v[2]);
            let t2 = s0.wrapping_add(maj);
            v = [t1.wrapping_add(t2), v[0], v[1], v[2], v[3].wrapping_add(t1), v[4], v[5], v[6]];
        }
        for i in 0..8 {
            h[i] = h[i].wrapping_add(v[i]);
        }
    }
    h.iter().map(|x| format!("{x:08x}")).collect()
}

// ---------------------------------------------------------------- checks

fn strings(v: &J, out: &mut Vec<String>) {
    match v {
        J::Str(s) => out.push(s.clone()),
        J::Arr(a) => a.iter().for_each(|x| strings(x, out)),
        J::Obj(m) => m.iter().for_each(|(k, x)| {
            out.push(k.clone());
            strings(x, out)
        }),
        _ => {}
    }
}

fn s<'a>(o: &'a BTreeMap<String, J>, k: &str) -> Option<&'a str> {
    match o.get(k) {
        Some(J::Str(x)) => Some(x),
        _ => None,
    }
}

/// Every failed check; empty means the geometry is authorised.
fn check(text: &str, root: &Path) -> Vec<String> {
    let mut e = Vec::new();
    let doc = match parse(text) {
        Ok(J::Obj(m)) => m,
        Ok(_) => return vec!["top level is not a JSON object".into()],
        Err(x) => return vec![format!("invalid JSON: {x}")],
    };
    let mut all = Vec::new();
    strings(&J::Obj(doc.clone()), &mut all);
    for f in FORBIDDEN {
        if all.iter().any(|x| x.to_ascii_uppercase().contains(f)) {
            e.push(format!("contains forbidden marker {f}"));
        }
    }
    if s(&doc, "status") != Some(STATUS) {
        e.push(format!("status is {:?}, not {STATUS:?}", doc.get("status")));
    }
    let segs = match doc.get("segments") {
        Some(J::Arr(a)) if !a.is_empty() => a,
        Some(J::Arr(_)) => {
            e.push("segments is empty".into());
            return e;
        }
        _ => {
            e.push("segments missing or not an array".into());
            return e;
        }
    };
    let mut ids = BTreeSet::new();
    let mut kinds = BTreeSet::new();
    let mut degree: BTreeMap<String, usize> = BTreeMap::new();
    let mut edges = Vec::new();
    for (n, seg) in segs.iter().enumerate() {
        let J::Obj(o) = seg else {
            e.push(format!("segment {n} is not an object"));
            continue;
        };
        let (Some(id), Some(kind), Some(a), Some(b)) = (s(o, "id"), s(o, "kind"), s(o, "from"), s(o, "to")) else {
            e.push(format!("segment {n} lacks string id/kind/from/to"));
            continue;
        };
        if !ids.insert(id.to_string()) {
            e.push(format!("duplicate segment id {id:?}"));
        }
        if a == b {
            e.push(format!("segment {id}: from == to ({a})"));
        }
        kinds.insert(kind.to_string());
        *degree.entry(a.to_string()).or_default() += 1;
        *degree.entry(b.to_string()).or_default() += 1;
        edges.push((a.to_string(), b.to_string()));
        let Some(J::Obj(p)) = o.get("provenance") else {
            e.push(format!("segment {id}: provenance missing"));
            continue;
        };
        match s(p, "class") {
            Some(c) if CLASSES.contains(&c) => {}
            c => e.push(format!("segment {id}: provenance class {c:?} not one of {CLASSES:?}")),
        }
        let (Some(src), Some(hash)) = (s(p, "source"), s(p, "sha256")) else {
            e.push(format!("segment {id}: provenance needs source and sha256"));
            continue;
        };
        if hash.len() != 64 || !hash.chars().all(|c| c.is_ascii_hexdigit()) {
            e.push(format!("segment {id}: sha256 is not 64 hex digits"));
            continue;
        }
        let rel = Path::new(src);
        if rel.is_absolute() || rel.components().any(|c| matches!(c, std::path::Component::ParentDir)) {
            e.push(format!("segment {id}: source {src:?} must be a relative path inside the root"));
            continue;
        }
        match fs::read(root.join(rel)) {
            Ok(bytes) if sha256(&bytes) == hash.to_ascii_lowercase() => {}
            Ok(_) => e.push(format!("segment {id}: source {src} does not match its sha256")),
            Err(_) => e.push(format!("segment {id}: source {src} not found under {}", root.display())),
        }
    }
    for k in REQUIRED_KINDS {
        if !kinds.contains(k) {
            e.push(format!("required segment kind {k} missing"));
        }
    }
    // One closed loop: every node degree 2 and the graph connected.
    if let Some((n, d)) = degree.iter().find(|(_, d)| **d != 2) {
        e.push(format!("node {n} has degree {d}; a closed current loop needs exactly 2"));
    }
    if let Some((start, _)) = edges.first() {
        let mut seen = BTreeSet::from([start.clone()]);
        let mut stack = vec![start.clone()];
        while let Some(n) = stack.pop() {
            for (a, b) in &edges {
                let next = if *a == n { b } else if *b == n { a } else { continue };
                if seen.insert(next.clone()) {
                    stack.push(next.clone());
                }
            }
        }
        if seen.len() != degree.len() {
            e.push(format!("segments form {} of {} nodes in one loop: not connected", seen.len(), degree.len()));
        }
    }
    e
}

fn main() {
    let a: Vec<_> = env::args().collect();
    if a.len() < 2 || a.len() > 3 {
        eprintln!("usage: geometry_gate <topology.json> [<root>]");
        process::exit(2);
    }
    let text = fs::read_to_string(&a[1]).unwrap_or_default();
    let root = Path::new(a.get(2).map(String::as_str).unwrap_or("."));
    let errs = check(&text, root);
    let ok = errs.is_empty();
    let list = errs.iter().map(|x| format!("{x:?}")).collect::<Vec<_>>().join(",");
    println!(
        "{{\"complete_physical_geometry\":{ok},\"field_solve_authorized\":{ok},\"failed_checks\":[{list}],\"reason\":\"holder/fuse internal path, diode die/bond, capacitor distribution and native-return closure must be physical geometry before complete installed inductance can be claimed\"}}"
    );
    if !ok {
        process::exit(3);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn root_with(files: &[(&str, &str)]) -> std::path::PathBuf {
        // a unique directory per call: tests run in parallel
        static N: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
        let n = N.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        let d = env::temp_dir().join(format!("geometry_gate_test_{}_{n}", process::id()));
        let _ = fs::remove_dir_all(&d);
        fs::create_dir_all(&d).unwrap();
        for (n, c) in files {
            fs::write(d.join(n), c).unwrap();
        }
        d
    }

    fn seg(id: &str, kind: &str, a: &str, b: &str, src: &str, hash: &str) -> String {
        format!(
            r#"{{"id":"{id}","kind":"{kind}","from":"{a}","to":"{b}","provenance":{{"class":"physical","source":"{src}","sha256":"{hash}"}}}}"#
        )
    }

    fn complete(hash: &str) -> String {
        let segs = [
            seg("s1", "fuse_holder_path", "n1", "n2", "cad.step", hash),
            seg("s2", "catch_diode_die_bond", "n2", "n3", "cad.step", hash),
            seg("s3", "catch_capacitor_distribution", "n3", "n4", "cad.step", hash),
            seg("s4", "native_return_closure", "n4", "n1", "cad.step", hash),
        ];
        format!(r#"{{"status":"{STATUS}","segments":[{}]}}"#, segs.join(","))
    }

    #[test]
    fn sha256_known_vectors() {
        assert_eq!(sha256(b""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
        assert_eq!(sha256(b"abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
    }

    #[test]
    fn complete_closed_loop_passes() {
        let root = root_with(&[("cad.step", "geometry")]);
        assert!(check(&complete(&sha256(b"geometry")), &root).is_empty());
    }

    #[test]
    fn empty_segments_rejected() {
        // the round-6 false pass
        let e = check(&format!(r#"{{"status":"{STATUS}","segments":[]}}"#), Path::new("."));
        assert!(e.iter().any(|x| x.contains("segments is empty")), "{e:?}");
    }

    #[test]
    fn omitted_segments_rejected() {
        let e = check(&format!(r#"{{"status":"{STATUS}"}}"#), Path::new("."));
        assert!(e.iter().any(|x| x.contains("segments missing")), "{e:?}");
    }

    #[test]
    fn lowercase_or_renamed_status_rejected() {
        let root = root_with(&[("cad.step", "geometry")]);
        let good = complete(&sha256(b"geometry"));
        for bad in [good.replace(STATUS, &STATUS.to_lowercase()), good.replace(STATUS, "COMPLETE")] {
            assert!(check(&bad, &root).iter().any(|x| x.contains("status")), "{bad}");
        }
    }

    #[test]
    fn missing_required_kind_rejected() {
        let root = root_with(&[("cad.step", "geometry")]);
        let bad = complete(&sha256(b"geometry")).replace("native_return_closure", "other_path");
        assert!(check(&bad, &root).iter().any(|x| x.contains("native_return_closure missing")));
    }

    #[test]
    fn hash_mismatch_and_missing_source_rejected() {
        let root = root_with(&[("cad.step", "geometry")]);
        let e = check(&complete(&sha256(b"other")), &root);
        assert!(e.iter().any(|x| x.contains("does not match its sha256")), "{e:?}");
        let e = check(&complete(&sha256(b"geometry")).replace("cad.step", "absent.step"), &root);
        assert!(e.iter().any(|x| x.contains("not found")), "{e:?}");
        let e = check(&complete(&sha256(b"geometry")).replace("cad.step", "../cad.step"), &root);
        assert!(e.iter().any(|x| x.contains("relative path inside the root")), "{e:?}");
    }

    #[test]
    fn open_loop_rejected() {
        let root = root_with(&[("cad.step", "geometry")]);
        let bad = complete(&sha256(b"geometry")).replace(r#""from":"n4","to":"n1""#, r#""from":"n4","to":"n5""#);
        assert!(check(&bad, &root).iter().any(|x| x.contains("degree")));
    }

    #[test]
    fn forbidden_marker_and_bad_class_rejected() {
        let root = root_with(&[("cad.step", "geometry")]);
        let good = complete(&sha256(b"geometry"));
        let e = check(&good.replacen("fuse_holder_path\"", "fuse_holder_path\",\"note\":\"approximation\"", 1), &root);
        assert!(e.iter().any(|x| x.contains("APPROXIMATION")), "{e:?}");
        let e = check(&good.replacen("\"physical\"", "\"assumed\"", 1), &root);
        assert!(e.iter().any(|x| x.contains("provenance class")), "{e:?}");
    }

    #[test]
    fn current_scaffold_style_rejected() {
        let e = check(r#"{"status":"PORT_CLOSURE_ONLY_SCAFFOLD","segments":[{"id":"x"}]}"#, Path::new("."));
        assert!(!e.is_empty());
    }

    #[test]
    fn malformed_json_rejected() {
        assert!(check("{\"status\": ", Path::new(".")).iter().any(|x| x.contains("invalid JSON")));
    }
}
