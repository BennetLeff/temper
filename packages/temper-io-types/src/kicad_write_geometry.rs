// kicad_write_geometry: the deterministic geometry/formatting kernels behind
// the KiCad s-expression WRITE surface, ported from
// `temper_placer/io/_write_tracks.py`, `_write_zones.py`, `_write_modules.py`
// and `placement_exporter.py` (Wave 4).
//
// The four Python modules are now delegation shims: they keep their public
// entry points (which stay on the Python side because they are kiutils board
// I/O — load a `.kicad_pcb`, mutate kiutils objects, write it back; the
// kiutils KiCad-format boundary is a documented JUSTIFIED-KEEP) and forward
// every *pure* kernel here. The differential
// `packages/temper-placer/tests/io/test_write_geometry_rust_differential.py`
// pins each kernel against the pre-migration implementation VERBATIM
// (`_oracle_*` blocks, origin/main `47349a50`).
//
// What is ported, and the boundary each port honours:
//
//   * `stable_tstamp` — the deterministic per-object UUID (`_stable_tstamp`).
//     sha256 of `"{kind}\0{key!r}"`, UUID v4 derived from the first 16 digest
//     bytes. `key!r` is CPython's `repr` — a Python runtime semantic (B9's
//     repr class) — so the repr is CALLED BACK across the boundary (`key.repr()`)
//     rather than reimplemented; the hashing and the UUID-v4 bit surgery are
//     native. This is the kernel that makes the written board byte-reproducible
//     (the pre-migration `uuid.uuid4()` made every write different).
//   * `trace_emission_key` / `via_emission_key` — the canonical emission order
//     of `(segment ...)` / `(via ...)` lines in the written board. The route /
//     via fields are read through Python's object protocol (`str()`,
//     `__float__()`, `__getitem__`) so numpy-typed geometry widens exactly as
//     the oracle's `float(route.start[0])` does; net index resolution and layer
//     rank are folded in. Both keys are total over the element set, which is
//     the whole determinism contract (`test_write_tracks_determinism.py`).
//   * `component_bounds` — the pad-bounding-box reduction from `_write_modules`
//     (`add_bounding_boxes_to_pcb` / `add_silkscreen_labels` share one
//     identical loop). The per-pad KiCad rotation (`rotate_local_to_world`, the
//     repo's SSOT for that convention) stays on the Python side and is passed
//     pre-rotated: it is `sin`/`cos` on `math.pi`, and B1 says libm and Rust's
//     intrinsics are not bit-identical across platforms for transcendentals —
//     the same judgement `dsn_exporter.rs` records for `pin_world_position`.
//     The reduction (order-sensitive `min`/`max` — B5, and the `abs_x - w/2`
//     operation order — B7) is ported.
//   * `zone_sexpr` — the `_write_zones.write_zones_to_pcb` per-zone
//     construction as the parsed s-expression tree kiutils' `Zone.from_sexpr`
//     consumes. Rust owns the semantic content (net/index, layer, tstamp,
//     polygon points, the implicit hatch/clearance/min_thickness defaults);
//     kiutils' own `to_sexpr` does the final serialisation, so float rendering
//     and quoting are never reimplemented (B1). Pinned byte-identical by
//     `tests/io/test_write_zones_rust_differential.py`.
//   * `build_net_name_to_index_map` / `resolve_net_index` — the net-name →
//     index mapping shared by `_write_zones.build_net_name_to_index_map` (and
//     inlined in `_write_tracks.write_routes_to_pcb`) plus the two index
//     resolutions (the truthiness-guarded `_resolve_net_index` and the zones
//     writer's bare `dict.get(net_name, 0)`). The kiutils reading (`hasattr`
//     guards) is reproduced via `getattr(...).ok()`.
//   * `rotation_index_to_degrees` / `placement_coordinate` — the placement
//     exporter's per-component arithmetic (`float(idx) * 90.0`; `x + origin_x`).
//     `np.argmax` (soft rotations → discrete indices) deliberately stays Python
//     — the same numpy-tie-break judgement `dsn_exporter.rs` records.
//
// The zone tstamp (`write_zones_to_pcb`'s `uuid.uuid4()`) is NOT touched: it
// is random in the pre-migration code, so determinizing it would be a behaviour
// change no bit-identical differential could pin, and the zone writer has no
// live caller. `zone_sexpr` therefore takes the tstamp as a parameter —
// recorded, not silently changed.

// Only `stable_tstamp` (below, `#[cfg(feature = "python")]`) hashes anything,
// so with `--no-default-features` -- the wasm32 configuration -- this import
// has no user and warns.  Gated on the same feature as its one call site
// rather than blanket-allowed, so a future pure caller re-enables it loudly.
#[cfg(feature = "python")]
use sha2::{Digest, Sha256};

/// The digest-to-UUIDv4 derivation behind `_stable_tstamp`: RFC 4122 v4 UUID
/// from the first 16 bytes of the sha256 digest.
///
/// Replicates `uuid.UUID(bytes=digest[:16], version=4)`: the version nibble
/// (4) is stamped into byte 6's high nibble and the variant (RFC 4122, `10b`)
/// into byte 8's top two bits, and the result renders as the canonical
/// 8-4-4-4-12 lowercase-hex form.
fn uuid_v4_from_first16(digest: &[u8]) -> String {
    let mut b = [0u8; 16];
    b.copy_from_slice(&digest[..16]);
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-\
         {:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9], b[10], b[11],
        b[12], b[13], b[14], b[15]
    )
}

/// Python `min(a, b)`: returns `a` unless `b < a` (order-sensitive around
/// NaN — CPython's min keeps the first argument when the comparison is
/// False). B5.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// Python `max(a, b)`: returns `a` unless `b > a`. B5.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// The pad-bounding-box reduction from `_write_modules`: min/max over the
/// pad-inclusive extents. `pads` are `(world_x, world_y, pad_w, pad_h)` —
/// already rotated by the Python SSOT. Operation order is load-bearing
/// (`abs_x - pad_w / 2` groups as `abs_x - (pad_w / 2)`; B7) and the
/// min/max are CPython-builtin semantics (B5).
fn component_bounds_pure(fp_x: f64, fp_y: f64, pads: &[(f64, f64, f64, f64)]) -> (f64, f64, f64, f64) {
    let mut x_min = f64::INFINITY;
    let mut y_min = f64::INFINITY;
    let mut x_max = f64::NEG_INFINITY;
    let mut y_max = f64::NEG_INFINITY;
    for &(rx, ry, pad_w, pad_h) in pads {
        let abs_x = fp_x + rx;
        let abs_y = fp_y + ry;
        x_min = py_min(x_min, abs_x - pad_w / 2.0);
        y_min = py_min(y_min, abs_y - pad_h / 2.0);
        x_max = py_max(x_max, abs_x + pad_w / 2.0);
        y_max = py_max(y_max, abs_y + pad_h / 2.0);
    }
    (x_min, y_min, x_max, y_max)
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod py_bridge {
    use super::*;
    use pyo3::exceptions::PyAttributeError;
    use pyo3::prelude::*;
    use pyo3::types::{PyBool, PyDict, PyList, PyTuple};
    use temper_py_bridge::catch_panic;

    /// Python `float(obj)` — exact CPython `float()` semantics (works on ints,
    /// floats and numpy scalars alike).
    fn py_float(obj: &Bound<'_, PyAny>) -> PyResult<f64> {
        obj.call_method0("__float__")?.extract::<f64>()
    }

    /// Python `str(obj)`.
    fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
        Ok(obj.str()?.to_string())
    }

    /// `int(obj)` via `__index__` — the integer-conversion protocol (ints,
    /// IntEnum members and numpy ints all implement it).
    fn py_index(obj: &Bound<'_, PyAny>) -> PyResult<i64> {
        obj.call_method0("__index__")?.extract::<i64>()
    }

    /// `d[k]` for a `net in map`-style lookup, returning `None` on a miss.
    /// The map is always a real `dict` at every call site (built by
    /// `build_net_name_to_index_map` or `LAYER_NAME_TO_IDX`), so it is typed
    /// as `PyDict` and read with `PyDictMethods::get_item`, whose `None`
    /// on a miss matches the oracle's `net in map` / `dict.get` fallbacks.
    fn map_get<'py>(map: &Bound<'py, PyDict>, key: &str) -> PyResult<Option<Bound<'py, PyAny>>> {
        map.get_item(key)
    }

    /// `[key, vals...]` — a single node of a kiutils parsed s-expression
    /// tree (the `list` form the `from_sexpr` constructors consume).
    fn node<'py>(
        py: Python<'py>,
        key: &str,
        vals: Vec<Bound<'py, PyAny>>,
    ) -> PyResult<Bound<'py, PyAny>> {
        let mut items: Vec<Bound<'py, PyAny>> = vec![key.into_pyobject(py)?.into_any()];
        items.extend(vals);
        Ok(PyList::new(py, items)?.into_any())
    }

    /// `_resolve_net_index`: `net and net in map` — a truthiness-guarded
    /// lookup that returns 0 for falsy or unknown nets.
    fn resolve_net_index(net: &Bound<'_, PyAny>, map: &Bound<'_, PyDict>) -> PyResult<i64> {
        if !net.is_truthy()? {
            return Ok(0);
        }
        let net_str = py_str(net)?;
        match map_get(map, &net_str)? {
            Some(v) => py_index(&v),
            None => Ok(0),
        }
    }

    /// `_layer_rank`: physical stackup rank by `LAYER_NAME_TO_IDX`, else the
    /// unranked fallback (layers outside the standard stackup sort after all
    /// of them, still totally ordered by name).
    fn layer_rank(
        layer: &Bound<'_, PyAny>,
        layer_name_to_index: &Bound<'_, PyDict>,
        unranked_layer: i64,
    ) -> PyResult<(i64, String)> {
        let name = py_str(layer)?;
        let rank = match map_get(layer_name_to_index, &name)? {
            Some(idx) => py_index(&idx)?,
            None => unranked_layer,
        };
        Ok((rank, name))
    }

    /// `_stable_tstamp`: `sha256(f"{kind}\x00{key!r}")` with a UUIDv4 derived
    /// from the digest's first 16 bytes. The repr is CPython's (called back).
    #[pyfunction]
    pub fn stable_tstamp_py(kind: &str, key: &Bound<'_, PyAny>) -> PyResult<String> {
        catch_panic(|| {
            let key_repr = key.repr()?.to_string();
            let payload = format!("{kind}\x00{key_repr}");
            let mut hasher = Sha256::new();
            hasher.update(payload.as_bytes());
            let digest = hasher.finalize();
            Ok(uuid_v4_from_first16(&digest))
        })
    }

    /// `_trace_emission_key`: the canonical emission key of a route.
    #[pyfunction]
    #[pyo3(signature = (route, net_name_to_index, layer_name_to_index, unranked_layer))]
    pub fn trace_emission_key_py(
        py: Python<'_>,
        route: &Bound<'_, PyAny>,
        net_name_to_index: &Bound<'_, PyDict>,
        layer_name_to_index: &Bound<'_, PyDict>,
        unranked_layer: i64,
    ) -> PyResult<Py<PyTuple>> {
        catch_panic(|| {
            let net_any = route.getattr("net")?;
            let net = if net_any.is_truthy()? {
                py_str(&net_any)?
            } else {
                String::new()
            };
            let net_index = resolve_net_index(&net_any, net_name_to_index)?;

            let layer = route.getattr("layer")?;
            let (rank, layer_name) = layer_rank(&layer, layer_name_to_index, unranked_layer)?;

            let start = route.getattr("start")?;
            let start_x = py_float(&start.get_item(0)?)?;
            let start_y = py_float(&start.get_item(1)?)?;
            let end = route.getattr("end")?;
            let end_x = py_float(&end.get_item(0)?)?;
            let end_y = py_float(&end.get_item(1)?)?;
            let width = py_float(&route.getattr("width")?)?;

            let rank_tup = PyTuple::new(py, [rank.into_pyobject(py)?.into_any(), layer_name.into_pyobject(py)?.into_any()])?;
            let start_tup = PyTuple::new(py, [start_x.into_pyobject(py)?.into_any(), start_y.into_pyobject(py)?.into_any()])?;
            let end_tup = PyTuple::new(py, [end_x.into_pyobject(py)?.into_any(), end_y.into_pyobject(py)?.into_any()])?;

            let items: Vec<Bound<'_, PyAny>> = vec![
                net_index.into_pyobject(py)?.into_any(),
                net.into_pyobject(py)?.into_any(),
                rank_tup.into_any(),
                start_tup.into_any(),
                end_tup.into_any(),
                width.into_pyobject(py)?.into_any(),
            ];
            let key = PyTuple::new(py, items)?;
            Ok(key.unbind())
        })
    }

    /// `_via_emission_key`: the canonical emission key of a via.
    #[pyfunction]
    #[pyo3(signature = (via, net_name_to_index))]
    pub fn via_emission_key_py(
        py: Python<'_>,
        via: &Bound<'_, PyAny>,
        net_name_to_index: &Bound<'_, PyDict>,
    ) -> PyResult<Py<PyTuple>> {
        catch_panic(|| {
            let net_any = via.getattr("net")?;
            let net = if net_any.is_truthy()? {
                py_str(&net_any)?
            } else {
                String::new()
            };
            let net_index = resolve_net_index(&net_any, net_name_to_index)?;

            let position = via.getattr("position")?;
            let pos_x = py_float(&position.get_item(0)?)?;
            let pos_y = py_float(&position.get_item(1)?)?;
            let drill = py_float(&via.getattr("drill")?)?;
            let width = py_float(&via.getattr("width")?)?;

            // `tuple(str(layer) for layer in via.layers)`
            let mut layer_strs = Vec::new();
            for layer in via.getattr("layers")?.try_iter()? {
                layer_strs.push(py_str(&layer?)?);
            }
            let layers_tup = PyTuple::new(py, layer_strs)?;

            // `bool(getattr(via, "is_diff_pair", False))` — a defaulted
            // getattr swallows only AttributeError (CPython semantics).
            let is_diff_pair = match via.getattr("is_diff_pair") {
                Ok(v) => v.is_truthy()?,
                Err(e) if e.is_instance_of::<PyAttributeError>(py) => false,
                Err(e) => return Err(e),
            };

            let pos_tup = PyTuple::new(py, [pos_x.into_pyobject(py)?.into_any(), pos_y.into_pyobject(py)?.into_any()])?;

            let items: Vec<Bound<'_, PyAny>> = vec![
                net_index.into_pyobject(py)?.into_any(),
                net.into_pyobject(py)?.into_any(),
                pos_tup.into_any(),
                drill.into_pyobject(py)?.into_any(),
                width.into_pyobject(py)?.into_any(),
                layers_tup.into_any(),
                PyBool::new(py, is_diff_pair).to_owned().into_any(),
            ];
            let key = PyTuple::new(py, items)?;
            Ok(key.unbind())
        })
    }

    /// `_resolve_net_index` as a standalone kernel (used by the `write_routes_to_pcb`
    /// shim for the emitted `(net ...)` field and its sort key).
    #[pyfunction]
    pub fn resolve_net_index_py(
        net: &Bound<'_, PyAny>,
        net_name_to_index: &Bound<'_, PyDict>,
    ) -> PyResult<i64> {
        catch_panic(|| resolve_net_index(net, net_name_to_index))
    }

    /// `net_name_to_index.get(net_name, 0)` — the zones writer's bare lookup.
    #[pyfunction]
    pub fn resolve_net_index_default_py(
        net_name: &str,
        net_name_to_index: &Bound<'_, PyDict>,
    ) -> PyResult<i64> {
        catch_panic(|| match map_get(net_name_to_index, net_name)? {
            Some(v) => py_index(&v),
            None => Ok(0),
        })
    }

    /// `build_net_name_to_index_map`'s loop: `if hasattr(net, "name") and
    /// hasattr(net, "number"): net_map[net.name] = net.number`. `hasattr` is
    /// reproduced as `getattr(...).ok()` (which, like CPython's `hasattr`,
    /// swallows any exception, not only AttributeError).
    #[pyfunction]
    pub fn build_net_name_to_index_map_py(
        py: Python<'_>,
        nets: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyDict>> {
        catch_panic(|| {
            let out = PyDict::new(py);
            for net in nets.try_iter()? {
                let net = net?;
                if let (Ok(name), Ok(number)) = (net.getattr("name"), net.getattr("number")) {
                    out.set_item(name, number)?;
                }
            }
            Ok(out.unbind())
        })
    }

    /// `_component_bounds`: the pad-bounding-box reduction over pre-rotated
    /// world-space pads `(wx, wy, pad_w, pad_h)`.
    #[pyfunction]
    pub fn component_bounds_py(
        fp_x: f64,
        fp_y: f64,
        world_pads: Vec<(f64, f64, f64, f64)>,
    ) -> PyResult<(f64, f64, f64, f64)> {
        catch_panic(|| Ok(component_bounds_pure(fp_x, fp_y, &world_pads)))
    }

    /// `_write_zones.write_zones_to_pcb`'s per-zone construction: the parsed
    /// s-expression tree that kiutils' `Zone.from_sexpr` consumes, mirroring
    /// `Zone(netName=..., net=..., layers=[...], tstamp=...,
    /// polygons=[ZonePolygon(coordinates=[...])], minThickness=0.254)`
    /// field-for-field (every other field at its dataclass default).
    ///
    /// Rust owns the zone's semantic content — the net name/index, layer,
    /// tstamp, polygon points and the implicit defaults (hatch none/0.0,
    /// clearance/min_thickness 0.254) — as a `list` structure; the Python
    /// shim materialises it with `Zone.from_sexpr` and kiutils' own
    /// `to_sexpr` does the final serialisation, so float rendering and
    /// quoting are never reimplemented in Rust (B1 discipline). The
    /// differential pins `Zone.from_sexpr(rust).to_sexpr()` byte-identical
    /// to the oracle's `Zone(...).to_sexpr()`.
    #[pyfunction]
    pub fn zone_sexpr_py(
        py: Python<'_>,
        net_name: &str,
        net: i64,
        layer: &str,
        tstamp: &str,
        points: Vec<(f64, f64)>,
    ) -> PyResult<Py<PyList>> {
        catch_panic(|| {
            let mut zone: Vec<Bound<'_, PyAny>> = Vec::new();
            zone.push("zone".into_pyobject(py)?.into_any());

            let net_item: Vec<Bound<'_, PyAny>> = vec![
                "net".into_pyobject(py)?.into_any(),
                net.into_pyobject(py)?.into_any(),
            ];
            zone.push(PyList::new(py, net_item)?.into_any());

            let net_name_item: Vec<Bound<'_, PyAny>> = vec![
                "net_name".into_pyobject(py)?.into_any(),
                net_name.into_pyobject(py)?.into_any(),
            ];
            zone.push(PyList::new(py, net_name_item)?.into_any());

            let layer_item: Vec<Bound<'_, PyAny>> = vec![
                "layer".into_pyobject(py)?.into_any(),
                layer.into_pyobject(py)?.into_any(),
            ];
            zone.push(PyList::new(py, layer_item)?.into_any());

            let tstamp_item: Vec<Bound<'_, PyAny>> = vec![
                "tstamp".into_pyobject(py)?.into_any(),
                tstamp.into_pyobject(py)?.into_any(),
            ];
            zone.push(PyList::new(py, tstamp_item)?.into_any());

            let hatch_item: Vec<Bound<'_, PyAny>> = vec![
                "hatch".into_pyobject(py)?.into_any(),
                "none".into_pyobject(py)?.into_any(),
                0.0f64.into_pyobject(py)?.into_any(),
            ];
            zone.push(PyList::new(py, hatch_item)?.into_any());

            let connect_item: Vec<Bound<'_, PyAny>> = vec![
                "connect_pads".into_pyobject(py)?.into_any(),
                PyList::new(
                    py,
                    [
                        "clearance".into_pyobject(py)?.into_any(),
                        0.254f64.into_pyobject(py)?.into_any(),
                    ],
                )?
                .into_any(),
            ];
            zone.push(PyList::new(py, connect_item)?.into_any());

            let min_thickness_item: Vec<Bound<'_, PyAny>> = vec![
                "min_thickness".into_pyobject(py)?.into_any(),
                0.254f64.into_pyobject(py)?.into_any(),
            ];
            zone.push(PyList::new(py, min_thickness_item)?.into_any());

            let mut pts: Vec<Bound<'_, PyAny>> = vec!["pts".into_pyobject(py)?.into_any()];
            for (x, y) in points {
                let xy: Vec<Bound<'_, PyAny>> = vec![
                    "xy".into_pyobject(py)?.into_any(),
                    x.into_pyobject(py)?.into_any(),
                    y.into_pyobject(py)?.into_any(),
                ];
                pts.push(PyList::new(py, xy)?.into_any());
            }
            let polygon_item: Vec<Bound<'_, PyAny>> = vec![
                "polygon".into_pyobject(py)?.into_any(),
                PyList::new(py, pts)?.into_any(),
            ];
            zone.push(PyList::new(py, polygon_item)?.into_any());

            Ok(PyList::new(py, zone)?.unbind())
        })
    }

    /// `_write_modules.add_bounding_boxes_to_pcb`'s per-rect construction: the
    /// parsed s-expression tree that kiutils' `GrRect.from_sexpr` consumes
    /// (`(gr_rect (start x y) (end x y) (layer L) (width W))`). Rust owns the
    /// content; kiutils' own `to_sexpr` does the serialisation (B1 — floats
    /// are carried as values, so the int-coercion of a text round-trip can
    /// never change the emitted bytes).
    #[pyfunction]
    pub fn gr_rect_sexpr_py(
        py: Python<'_>,
        x_min: f64,
        y_min: f64,
        x_max: f64,
        y_max: f64,
        layer: &str,
        width: f64,
    ) -> PyResult<Py<PyList>> {
        catch_panic(|| {
            let mut gr_rect: Vec<Bound<'_, PyAny>> = vec!["gr_rect".into_pyobject(py)?.into_any()];
            gr_rect.push(node(
                py,
                "start",
                vec![
                    x_min.into_pyobject(py)?.into_any(),
                    y_min.into_pyobject(py)?.into_any(),
                ],
            )?);
            gr_rect.push(node(
                py,
                "end",
                vec![
                    x_max.into_pyobject(py)?.into_any(),
                    y_max.into_pyobject(py)?.into_any(),
                ],
            )?);
            gr_rect.push(node(py, "layer", vec![layer.into_pyobject(py)?.into_any()])?);
            gr_rect.push(node(py, "width", vec![width.into_pyobject(py)?.into_any()])?);
            Ok(PyList::new(py, gr_rect)?.unbind())
        })
    }

    /// `_write_modules.add_silkscreen_labels`'s per-text construction: the
    /// parsed s-expression tree that kiutils' `GrText.from_sexpr` consumes
    /// (`(gr_text "T" (at x y) (layer L) (effects (font (size 1.0 1.0))))`).
    /// The `effects` node reproduces the dataclass default `Font(size=1.0,
    /// 1.0)` that `to_sexpr` emits. See [`gr_rect_sexpr_py`] for the float
    /// rationale.
    #[pyfunction]
    pub fn gr_text_sexpr_py(
        py: Python<'_>,
        text: &str,
        x: f64,
        y: f64,
        layer: &str,
    ) -> PyResult<Py<PyList>> {
        catch_panic(|| {
            let mut gr_text: Vec<Bound<'_, PyAny>> = vec![
                "gr_text".into_pyobject(py)?.into_any(),
                text.into_pyobject(py)?.into_any(),
            ];
            gr_text.push(node(
                py,
                "at",
                vec![x.into_pyobject(py)?.into_any(), y.into_pyobject(py)?.into_any()],
            )?);
            gr_text.push(node(py, "layer", vec![layer.into_pyobject(py)?.into_any()])?);
            let effects = node(
                py,
                "effects",
                vec![node(
                    py,
                    "font",
                    vec![node(
                        py,
                        "size",
                        vec![
                            1.0f64.into_pyobject(py)?.into_any(),
                            1.0f64.into_pyobject(py)?.into_any(),
                        ],
                    )?],
                )?],
            )?;
            gr_text.push(effects);
            Ok(PyList::new(py, gr_text)?.unbind())
        })
    }

    /// `_write_tracks.write_routes_to_pcb`'s per-segment construction: the
    /// parsed s-expression tree that kiutils' `Segment.from_sexpr` consumes
    /// (`(segment (start x y) (end x y) (width w) (layer L) (net N) (tstamp
    /// T))`). Rust owns the content; kiutils' own `to_sexpr` does the
    /// serialisation (B1 — floats are carried as values, so the int-coercion
    /// of a text round-trip can never change the emitted bytes).
    #[pyfunction]
    pub fn segment_sexpr_py(
        py: Python<'_>,
        start_x: f64,
        start_y: f64,
        end_x: f64,
        end_y: f64,
        width: f64,
        layer: &str,
        net: i64,
        tstamp: &str,
    ) -> PyResult<Py<PyList>> {
        catch_panic(|| {
            let mut segment: Vec<Bound<'_, PyAny>> =
                vec!["segment".into_pyobject(py)?.into_any()];
            segment.push(node(
                py,
                "start",
                vec![
                    start_x.into_pyobject(py)?.into_any(),
                    start_y.into_pyobject(py)?.into_any(),
                ],
            )?);
            segment.push(node(
                py,
                "end",
                vec![
                    end_x.into_pyobject(py)?.into_any(),
                    end_y.into_pyobject(py)?.into_any(),
                ],
            )?);
            segment.push(node(py, "width", vec![width.into_pyobject(py)?.into_any()])?);
            segment.push(node(py, "layer", vec![layer.into_pyobject(py)?.into_any()])?);
            segment.push(node(py, "net", vec![net.into_pyobject(py)?.into_any()])?);
            segment.push(node(py, "tstamp", vec![tstamp.into_pyobject(py)?.into_any()])?);
            Ok(PyList::new(py, segment)?.unbind())
        })
    }

    /// `_write_tracks.write_routes_to_pcb`'s per-via construction: the
    /// parsed s-expression tree that kiutils' `Via.from_sexpr` consumes
    /// (`(via (at x y) (size s) (drill d) (layers L1 L2) (net N) (tstamp
    /// T))`). See [`segment_sexpr_py`] for the float rationale.
    #[pyfunction]
    pub fn via_sexpr_py(
        py: Python<'_>,
        x: f64,
        y: f64,
        size: f64,
        drill: f64,
        layers: Vec<String>,
        net: i64,
        tstamp: &str,
    ) -> PyResult<Py<PyList>> {
        catch_panic(|| {
            let mut via: Vec<Bound<'_, PyAny>> = vec!["via".into_pyobject(py)?.into_any()];
            via.push(node(
                py,
                "at",
                vec![x.into_pyobject(py)?.into_any(), y.into_pyobject(py)?.into_any()],
            )?);
            via.push(node(py, "size", vec![size.into_pyobject(py)?.into_any()])?);
            via.push(node(py, "drill", vec![drill.into_pyobject(py)?.into_any()])?);
            let mut layers_node: Vec<Bound<'_, PyAny>> =
                vec!["layers".into_pyobject(py)?.into_any()];
            for layer in layers {
                layers_node.push(layer.into_pyobject(py)?.into_any());
            }
            via.push(PyList::new(py, layers_node)?.into_any());
            via.push(node(py, "net", vec![net.into_pyobject(py)?.into_any()])?);
            via.push(node(py, "tstamp", vec![tstamp.into_pyobject(py)?.into_any()])?);
            Ok(PyList::new(py, via)?.unbind())
        })
    }

    /// `_write_board.add_isolation_slots_to_pcb`'s per-slot construction: the
    /// parsed s-expression tree that kiutils' `GrLine.from_sexpr` consumes
    /// (`(gr_line (start x y) (end x y) (layer L) (width W))`). See
    /// [`segment_sexpr_py`] for the float rationale.
    #[pyfunction]
    pub fn gr_line_sexpr_py(
        py: Python<'_>,
        start_x: f64,
        start_y: f64,
        end_x: f64,
        end_y: f64,
        layer: &str,
        width: f64,
    ) -> PyResult<Py<PyList>> {
        catch_panic(|| {
            let mut gr_line: Vec<Bound<'_, PyAny>> = vec!["gr_line".into_pyobject(py)?.into_any()];
            gr_line.push(node(
                py,
                "start",
                vec![
                    start_x.into_pyobject(py)?.into_any(),
                    start_y.into_pyobject(py)?.into_any(),
                ],
            )?);
            gr_line.push(node(
                py,
                "end",
                vec![
                    end_x.into_pyobject(py)?.into_any(),
                    end_y.into_pyobject(py)?.into_any(),
                ],
            )?);
            gr_line.push(node(py, "layer", vec![layer.into_pyobject(py)?.into_any()])?);
            gr_line.push(node(py, "width", vec![width.into_pyobject(py)?.into_any()])?);
            Ok(PyList::new(py, gr_line)?.unbind())
        })
    }

    /// `_kicad_exporter.add_segments_to_board` / `add_vias_to_board`'s
    /// net-code lookup (the first `for net in board.nets` loop in each):
    ///
    /// ```python
    /// net_code = 0  # Default to unconnected
    /// for net in board.nets:
    ///     if net.name == seg.net:
    ///         net_code = net.number
    ///         break
    /// ```
    ///
    /// First match wins; no match yields 0 (unconnected). `net.name` /
    /// `net.number` are read through the Python object protocol (the D5
    /// duck-typed boundary) — a missing `name` attribute propagates, exactly
    /// as the Python loop would.
    #[pyfunction]
    pub fn find_net_code_py(
        py: Python<'_>,
        nets: &Bound<'_, PyAny>,
        net_name: &str,
    ) -> PyResult<i64> {
        catch_panic(|| {
            for net in nets.try_iter()? {
                let net = net?;
                let name = net.getattr("name")?;
                if name.eq(net_name)? {
                    return py_index(&net.getattr("number")?);
                }
            }
            Ok(0)
        })
    }

    /// `float(index) * 90.0` — rotation index to degrees.
    #[pyfunction]
    pub fn rotation_index_to_degrees_py(index: i64) -> PyResult<f64> {
        catch_panic(|| Ok(index as f64 * 90.0))
    }

    /// `x + origin_x`, `y + origin_y` — the placement exporter's coordinate
    /// offset (origin applied after the caller's `float()` extraction).
    #[pyfunction]
    pub fn placement_coordinate_py(
        x: f64,
        y: f64,
        origin_x: f64,
        origin_y: f64,
    ) -> PyResult<(f64, f64)> {
        catch_panic(|| Ok((x + origin_x, y + origin_y)))
    }

    pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
        let py = module.py();
        let sub = PyModule::new(py, "kicad_write_geometry")?;
        sub.add_function(wrap_pyfunction!(stable_tstamp_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(trace_emission_key_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(via_emission_key_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(resolve_net_index_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(resolve_net_index_default_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(build_net_name_to_index_map_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(component_bounds_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(zone_sexpr_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(gr_rect_sexpr_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(gr_text_sexpr_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(segment_sexpr_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(via_sexpr_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(gr_line_sexpr_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(find_net_code_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(rotation_index_to_degrees_py, &sub)?)?;
        sub.add_function(wrap_pyfunction!(placement_coordinate_py, &sub)?)?;
        module.add_submodule(&sub)
    }
}

#[cfg(feature = "python")]
pub use py_bridge::register;

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn uuid_v4_from_first16_sets_version_and_variant() {
        // All-zero digest bytes: version 4 and RFC 4122 variant are stamped
        // in regardless of the source bytes.
        let s = uuid_v4_from_first16(&[0u8; 32]);
        assert_eq!(s.len(), 36);
        let b: Vec<&str> = s.split('-').collect();
        assert_eq!(b.len(), 5);
        assert_eq!(b[0].len(), 8);
        assert_eq!(b[1].len(), 4);
        assert_eq!(b[2].len(), 4);
        assert_eq!(b[3].len(), 4);
        assert_eq!(b[4].len(), 12);
        assert_eq!(&s[14..15], "4", "version nibble");
        assert!(matches!(s.chars().nth(19), Some('8' | '9' | 'a' | 'b')), "variant nibble");
        assert_eq!(s, s.to_lowercase(), "lowercase hex");
    }

    #[cfg_attr(test, test)]
    fn uuid_v4_from_first16_distinguishes_any_input_bit() {
        let a = uuid_v4_from_first16(&[0u8; 32]);
        let mut b = [0u8; 32];
        b[15] = 1;
        let c = uuid_v4_from_first16(&b);
        assert_ne!(a, c, "a difference in the 16th byte must change the UUID");
    }

    #[cfg_attr(test, test)]
    fn component_bounds_pure_keeps_first_argument_semantics() {
        // NaN pads: CPython's min keeps the first argument, so an inf seed
        // survives a NaN candidate (B5).
        let (x_min, y_min, x_max, y_max) =
            component_bounds_pure(0.0, 0.0, &[(f64::NAN, 0.0, 0.5, 0.5)]);
        assert_eq!(x_min, f64::INFINITY);
        assert_eq!(x_max, f64::NEG_INFINITY);
        assert!(y_min.is_finite() && y_max.is_finite());
    }

    #[cfg_attr(test, test)]
    fn component_bounds_pure_empty_pads_are_inf() {
        let b = component_bounds_pure(1.0, 2.0, &[]);
        assert_eq!(b, (f64::INFINITY, f64::INFINITY, f64::NEG_INFINITY, f64::NEG_INFINITY));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("kicad_write_geometry::tests::uuid_v4_from_first16_sets_version_and_variant", uuid_v4_from_first16_sets_version_and_variant),
        ("kicad_write_geometry::tests::uuid_v4_from_first16_distinguishes_any_input_bit", uuid_v4_from_first16_distinguishes_any_input_bit),
        ("kicad_write_geometry::tests::component_bounds_pure_keeps_first_argument_semantics", component_bounds_pure_keeps_first_argument_semantics),
        ("kicad_write_geometry::tests::component_bounds_pure_empty_pads_are_inf", component_bounds_pure_empty_pads_are_inf),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
