//! Bounded routing escapes for two-pad HOT components.
//!
//! A certified component may have less than the board's functional spacing
//! between its own pads. An escape area covers the pad's copper bounds and
//! extends from its outer edge only *away* from the other pad. Copper wholly
//! inside that area cannot decrease
//! the component's existing pad-to-pad copper gap. The generated KiCad rule
//! applies only to the component's exact two nets and only to whole tracks
//! enclosed by these named areas. Qualification of that component gap is a
//! separate decision; this module makes no certification claim.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

const EDGE_INSET_NM: i64 = 10_000;
const AREA_PREFIX: &str = "PE_";

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct RectNm {
    pub min_x: i64,
    pub min_y: i64,
    pub max_x: i64,
    pub max_y: i64,
}

impl RectNm {
    fn valid(self) -> bool {
        self.min_x < self.max_x && self.min_y < self.max_y
    }
}

#[derive(Debug, Deserialize)]
pub struct Pad {
    pub reference: String,
    pub number: String,
    pub net: String,
    pub centre: [i64; 2],
    pub orientation_deg: f64,
    pub bbox: RectNm,
    pub shape: String,
    pub front_smd: bool,
}

#[derive(Debug, Deserialize)]
pub struct Request {
    pub reference: String,
    pub outward_nm: i64,
    pub board_floor_nm: i64,
    /// Explicit pad-number/net contract, independent of the saved board.
    pub pad_nets: BTreeMap<String, String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Area {
    pub name: String,
    pub rect: RectNm,
}

#[derive(Debug, Deserialize)]
pub struct Input {
    pub requests: Vec<Request>,
    pub pads: Vec<Pad>,
    /// Present in verify mode; all observed PE_ rule areas, not a subset.
    pub actual_areas: Option<Vec<Area>>,
}

#[derive(Debug, Serialize)]
pub struct Plan {
    pub areas: Vec<Area>,
    pub rules: String,
}

fn validate_pad(pad: &Pad) -> Result<(), String> {
    if !pad.orientation_deg.is_finite()
        || (pad.orientation_deg / 90.0 - (pad.orientation_deg / 90.0).round()).abs() > 1e-9
    {
        return Err(format!(
            "{} pad {} must have orthogonal copper orientation",
            pad.reference, pad.number
        ));
    }
    if !pad.front_smd || !matches!(pad.shape.as_str(), "rect" | "roundrect") {
        return Err(format!(
            "{} pad {} must be a front SMD rectangle or rounded rectangle",
            pad.reference, pad.number
        ));
    }
    if !safe_net(&pad.net) || pad.number.is_empty() || !pad.bbox.valid() {
        return Err(format!(
            "{} pad {} has invalid identity or bounds",
            pad.reference, pad.number
        ));
    }
    if pad.centre[0] <= pad.bbox.min_x
        || pad.centre[0] >= pad.bbox.max_x
        || pad.centre[1] <= pad.bbox.min_y
        || pad.centre[1] >= pad.bbox.max_y
    {
        return Err(format!(
            "{} pad {} centre is outside copper bounds",
            pad.reference, pad.number
        ));
    }
    Ok(())
}

fn safe_net(net: &str) -> bool {
    !net.is_empty()
        && net
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

fn area_for(pad: &Pad, other: &Pad, axis_x: bool, extension: i64) -> Result<Area, String> {
    let mut rect = pad.bbox;
    if axis_x {
        rect.min_y += EDGE_INSET_NM;
        rect.max_y -= EDGE_INSET_NM;
        if pad.centre[0] < other.centre[0] {
            rect.min_x -= extension;
        } else {
            rect.max_x += extension;
        }
    } else {
        rect.min_x += EDGE_INSET_NM;
        rect.max_x -= EDGE_INSET_NM;
        if pad.centre[1] < other.centre[1] {
            rect.min_y -= extension;
        } else {
            rect.max_y += extension;
        }
    }
    if !rect.valid() {
        return Err(format!(
            "{} pad {} is too small for an escape area",
            pad.reference, pad.number
        ));
    }
    Ok(Area {
        name: format!("{AREA_PREFIX}{}_{}", pad.reference, pad.number),
        rect,
    })
}

fn axial_gap(first: RectNm, second: RectNm, axis_x: bool) -> i64 {
    if axis_x {
        if first.min_x < second.min_x {
            second.min_x - first.max_x
        } else {
            first.min_x - second.max_x
        }
    } else if first.min_y < second.min_y {
        second.min_y - first.max_y
    } else {
        first.min_y - second.max_y
    }
}

fn member(refdes: &str, net: &str, side: &str) -> String {
    format!(
        "{side}.Type == 'Pad' && {side}.memberOfFootprint('{refdes}') && {side}.NetName == '{net}'"
    )
}

fn enclosed(area: &str, net: &str, side: &str) -> String {
    format!(
        "{side}.Type == 'Track' && {side}.NetName == '{net}' && {side}.enclosedByArea('{area}')"
    )
}

fn pair_rule(reference: &str, pads: [&Pad; 2], areas: [&Area; 2], gap_nm: i64) -> String {
    let mut terms = Vec::new();
    for index in 0..2 {
        let other = 1 - index;
        terms.push(format!(
            "({} && {})",
            member(reference, &pads[other].net, "A"),
            enclosed(&areas[index].name, &pads[index].net, "B")
        ));
        terms.push(format!(
            "({} && {})",
            member(reference, &pads[other].net, "B"),
            enclosed(&areas[index].name, &pads[index].net, "A")
        ));
    }
    terms.push(format!(
        "({} && {})",
        enclosed(&areas[0].name, &pads[0].net, "A"),
        enclosed(&areas[1].name, &pads[1].net, "B")
    ));
    terms.push(format!(
        "({} && {})",
        enclosed(&areas[0].name, &pads[0].net, "B"),
        enclosed(&areas[1].name, &pads[1].net, "A")
    ));
    format!(
        "(rule \"{reference} bounded pad escapes: intrinsic component gap\"\n  (condition \"{}\")\n  (constraint clearance (min {:.6}mm)))",
        terms.join(" || "),
        gap_nm as f64 / 1_000_000.0
    )
}

/// Plan all requested areas and fail if observed areas have drifted.
pub fn plan(input: &Input) -> Result<Plan, String> {
    let mut by_ref: BTreeMap<&str, Vec<&Pad>> = BTreeMap::new();
    for pad in &input.pads {
        by_ref.entry(&pad.reference).or_default().push(pad);
    }
    let mut areas = Vec::new();
    let mut rules = Vec::new();
    let mut seen = BTreeSet::new();
    for request in &input.requests {
        let reference = request.reference.as_str();
        if !reference.chars().all(|c| c.is_ascii_alphanumeric()) || !seen.insert(reference) {
            return Err(format!("invalid or repeated reference {reference}"));
        }
        if request.outward_nm <= 0
            || request.board_floor_nm < 200_000
            || request.outward_nm > request.board_floor_nm
            || request.board_floor_nm > 5_000_000
        {
            return Err(format!(
                "{reference} escape length or board floor is out of range"
            ));
        }
        let pads = by_ref
            .get(reference)
            .ok_or_else(|| format!("{reference} is absent"))?;
        if pads.len() != 2 {
            return Err(format!("{reference} must have exactly two physical pads"));
        }
        let [a, b] = [pads[0], pads[1]];
        validate_pad(a)?;
        validate_pad(b)?;
        if a.net == b.net
            || a.number == b.number
            || !a.number.chars().all(|c| c.is_ascii_alphanumeric())
            || !b.number.chars().all(|c| c.is_ascii_alphanumeric())
        {
            return Err(format!(
                "{reference} pads must have distinct, simple numbers and nets"
            ));
        }
        if request.pad_nets.len() != 2
            || request.pad_nets.get(&a.number) != Some(&a.net)
            || request.pad_nets.get(&b.number) != Some(&b.net)
        {
            return Err(format!("{reference} pad number/net contract changed"));
        }
        let axis_x = if a.centre[1] == b.centre[1] && a.centre[0] != b.centre[0] {
            true
        } else if a.centre[0] == b.centre[0] && a.centre[1] != b.centre[1] {
            false
        } else {
            return Err(format!("{reference} pad centres are not axis aligned"));
        };
        let gap = axial_gap(a.bbox, b.bbox, axis_x);
        if gap < 200_000 || gap >= request.board_floor_nm {
            return Err(format!(
                "{reference} intrinsic pad gap is invalid or needs no exception"
            ));
        }
        let first = area_for(a, b, axis_x, request.outward_nm)?;
        let second = area_for(b, a, axis_x, request.outward_nm)?;
        if axial_gap(first.rect, b.bbox, axis_x) < gap
            || axial_gap(second.rect, a.bbox, axis_x) < gap
            || axial_gap(first.rect, second.rect, axis_x) < gap
        {
            return Err(format!(
                "{reference} escape geometry decreases the intrinsic pad gap"
            ));
        }
        rules.push(pair_rule(reference, [a, b], [&first, &second], gap));
        areas.extend([first, second]);
    }
    areas.sort_by(|a, b| a.name.cmp(&b.name));
    if let Some(actual) = &input.actual_areas {
        let mut observed = actual.clone();
        observed.sort_by(|a, b| a.name.cmp(&b.name));
        if observed != areas {
            return Err("observed pad escape rule areas differ from validated pad geometry".into());
        }
    }
    Ok(Plan {
        areas,
        rules: rules.join("\n\n"),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> Input {
        Input {
            requests: vec![Request {
                reference: "R27".into(),
                outward_nm: 800_000,
                board_floor_nm: 3_200_000,
                pad_nets: BTreeMap::from([
                    ("1".into(), "vdiv_1".into()),
                    ("2".into(), "vdiv_2".into()),
                ]),
            }],
            pads: vec![
                Pad {
                    reference: "R27".into(),
                    number: "1".into(),
                    net: "vdiv_1".into(),
                    centre: [52_000_000, 79_237_500],
                    orientation_deg: 90.0,
                    bbox: RectNm {
                        min_x: 51_125_000,
                        max_x: 52_875_000,
                        min_y: 78_675_000,
                        max_y: 79_800_000,
                    },
                    shape: "roundrect".into(),
                    front_smd: true,
                },
                Pad {
                    reference: "R27".into(),
                    number: "2".into(),
                    net: "vdiv_2".into(),
                    centre: [52_000_000, 82_162_500],
                    orientation_deg: 90.0,
                    bbox: RectNm {
                        min_x: 51_125_000,
                        max_x: 52_875_000,
                        min_y: 81_600_000,
                        max_y: 82_725_000,
                    },
                    shape: "roundrect".into(),
                    front_smd: true,
                },
            ],
            actual_areas: None,
        }
    }

    #[test]
    fn escape_area_extends_only_away_from_opposite_pad() {
        let result = plan(&fixture()).unwrap();
        assert_eq!(result.areas[0].rect.max_y, 79_800_000);
        assert_eq!(result.areas[0].rect.min_y, 77_875_000);
        assert!(axial_gap(result.areas[0].rect, result.areas[1].rect, false) >= 1_800_000);
        assert!(result.rules.contains("clearance (min 1.800000mm)"));
    }

    #[test]
    fn nonorthogonal_pad_body_fails_even_with_axis_aligned_centres() {
        let mut input = fixture();
        for angle in [45.0, 30.0, f64::NAN, f64::INFINITY] {
            input.pads[0].orientation_deg = angle;
            assert!(plan(&input).unwrap_err().contains("orthogonal"));
        }
        for angle in [0.0, 90.0, 180.0, 270.0, -90.0] {
            input.pads[0].orientation_deg = angle;
            assert!(plan(&input).is_ok());
        }
    }

    #[test]
    fn moved_or_enlarged_rule_area_fails_verification() {
        let mut input = fixture();
        let mut areas = plan(&input).unwrap().areas;
        areas[0].rect.max_y += 1;
        input.actual_areas = Some(areas);
        assert!(plan(&input).is_err());
    }

    #[test]
    fn wrong_pad_net_fails_verification() {
        let mut input = fixture();
        let areas = plan(&input).unwrap().areas;
        input.pads[0].net = "foreign".into();
        input.actual_areas = Some(areas);
        assert!(plan(&input).is_err());
    }

    #[test]
    fn condition_metacharacters_in_net_fail_closed() {
        let mut input = fixture();
        input.pads[0].net = "vdiv_1' || A.NetName == 'pe".into();
        input.requests[0]
            .pad_nets
            .insert("1".into(), input.pads[0].net.clone());
        assert!(plan(&input).is_err());
    }
}
