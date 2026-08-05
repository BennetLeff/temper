// Wave-4 Phase-5 report-surface migration (temper-io-types).
//
// Migrates the compute of `temper_placer/report/{formatter,generator,
// summary}.py` bit-identically into this crate. The Python modules become
// delegation shims; the pre-migration implementations are pinned verbatim as
// the differential oracles (`tests/report/_*_py_oracle.py`).
//
// Boundary decisions (argued in-source and in VERIFICATION.md):
//   - `json.dumps` / `json.dump` stay Python stdlib. The Rust side returns
//     the JSON *data* (a Python dict); the shim renders it. This keeps
//     PyYAML/json.dumps on the Python side per the established rulings and
//     makes int-vs-float leaf types and key insertion order explicit in the
//     differential (`test_json_shape_and_leaf_types_identical`).
//   - `str(value)` of arbitrary Python objects (metrics, affected items,
//     board dims) is a Python runtime semantic: the Rust code calls
//     `value.str()` back across the boundary instead of reimplementing it.
//   - `generate_text_report` stays Python: Rich console rendering is a
//     library semantic, not reimplementable (guide's "library semantics are
//     not reimplementable", same family as PyYAML).
//   - `datetime.now().strftime` in `BenchmarkSummary` stays Python (the
//     shim's dataclass default).
//   - `opt_result.history[-1]` indexing and `.get(key, default)` on the
//     loss/human-metrics dicts happen in Rust via pyo3 (PyList last item,
//     PyDict get with fallback) — same semantics, including the default
//     evaluation order (nested `.get` for total_hpwl_mm).
//
// Float formatting goes through `crate::pyfmt` (round-half-even, lowercase
// nan/inf).

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::pyfmt::{py_float_fmt_1, py_float_fmt_2, py_float_fmt_3};

// ---------------------------------------------------------------------------
// Small pyo3 helpers
// ---------------------------------------------------------------------------

/// `obj.name` extracted as `str` (Python runtime semantics).
fn get_str(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<String> {
    obj.getattr(name)?.extract::<String>()
}

/// `obj.name` as f64 via Python's `float()` (so ints and floats both work).
fn get_f64(obj: &Bound<'_, PyAny>, name: &str) -> PyResult<f64> {
    to_f64(&obj.getattr(name)?)
}

/// Python `float(obj)`.
pub(crate) fn to_f64(obj: &Bound<'_, PyAny>) -> PyResult<f64> {
    obj.call_method0("__float__")?.extract::<f64>()
}

/// Python `str(obj)`.
pub(crate) fn py_str(obj: &Bound<'_, PyAny>) -> PyResult<String> {
    Ok(obj.str()?.to_string())
}

/// Python `min(a, b)`: returns `a` unless `b < a` (order-sensitive around
/// NaN — CPython's min keeps the first arg when the comparison is False).
fn py_min(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// `obj.severity.name` for a drc_result.Issue.
fn severity_name(issue: &Bound<'_, PyAny>) -> PyResult<String> {
    let sev = issue.getattr("severity")?;
    get_str(&sev, "name")
}

/// Iterate a Python iterable's items.
pub(crate) fn iter_items<'py>(obj: &Bound<'py, PyAny>) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let mut out = Vec::new();
    for item in obj.try_iter()? {
        out.push(item?);
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// formatter.py
// ---------------------------------------------------------------------------

fn format_text_impl(result: &Bound<'_, PyAny>) -> PyResult<String> {
    let mut lines: Vec<String> = vec![
        "=".repeat(80),
        "temper-drc Check Report".to_string(),
        "=".repeat(80),
    ];
    lines.push(String::new());

    let check_results = iter_items(&result.getattr("check_results")?)?;
    let total_checks = check_results.len();
    let passed_checks = check_results
        .iter()
        .filter(|r| {
            r.getattr("passed")
                .map(|p| p.is_truthy().unwrap_or(false))
                .unwrap_or(false)
        })
        .count();
    let failed_checks = total_checks - passed_checks;
    let all_issues = iter_items(&result.getattr("all_issues")?)?;
    let total_issues = all_issues.len();
    let mut critical_issues = 0usize;
    let mut error_issues = 0usize;
    let mut warning_issues = 0usize;
    for r in &check_results {
        for issue in iter_items(&r.getattr("issues")?)? {
            match severity_name(&issue)?.as_str() {
                "CRITICAL" => critical_issues += 1,
                "ERROR" => error_issues += 1,
                "WARNING" => warning_issues += 1,
                _ => {}
            }
        }
    }

    let passed = result.getattr("passed")?.is_truthy()?;
    lines.push(format!("Status: {}", if passed { "PASS" } else { "FAIL" }));
    lines.push(format!(
        "Checks: {passed_checks} passed, {failed_checks} failed (out of {total_checks})"
    ));
    lines.push(format!("Issues: {total_issues} total"));
    if critical_issues > 0 {
        lines.push(format!("  - {critical_issues} CRITICAL"));
    }
    if error_issues > 0 {
        lines.push(format!("  - {error_issues} ERROR"));
    }
    if warning_issues > 0 {
        lines.push(format!("  - {warning_issues} WARNING"));
    }
    lines.push(format!(
        "Runtime: {}ms",
        py_float_fmt_1(get_f64(result, "total_elapsed_ms")?)
    ));
    lines.push(String::new());

    if !check_results.is_empty() {
        lines.push("-".repeat(80));
        lines.push("Check Results:".to_string());
        lines.push("-".repeat(80));

        for check_result in &check_results {
            let cr_passed = check_result.getattr("passed")?.is_truthy()?;
            let status_symbol = if cr_passed { "\u{2713}" } else { "\u{2717}" };
            let elapsed = py_float_fmt_1(get_f64(check_result, "elapsed_ms")?);
            lines.push(format!(
                "{status_symbol} {} ({elapsed}ms)",
                get_str(check_result, "check_name")?
            ));

            let issues = iter_items(&check_result.getattr("issues")?)?;
            if !issues.is_empty() {
                for issue in &issues {
                    let severity_label = severity_name(issue)?;
                    let code = get_str(issue, "code")?;
                    let message = get_str(issue, "message")?;
                    lines.push(format!("    [{severity_label}] {code}: {message}"));
                    let affected = iter_items(&issue.getattr("affected_items")?)?;
                    if !affected.is_empty() {
                        let joined = affected
                            .iter()
                            .map(|a| py_str(a))
                            .collect::<PyResult<Vec<_>>>()?
                            .join(", ");
                        lines.push(format!("      Affected: {joined}"));
                    }
                    let location = issue.getattr("location")?;
                    if !location.is_none() {
                        let x = py_float_fmt_2(get_f64(&location, "x")?);
                        let y = py_float_fmt_2(get_f64(&location, "y")?);
                        lines.push(format!("      Location: ({x}, {y})"));
                    }
                }
            }

            lines.push(String::new());
        }
    }

    let metrics_exist = check_results.iter().any(|r| {
        r.getattr("metrics")
            .map(|m| m.is_truthy().unwrap_or(false))
            .unwrap_or(false)
    });
    if metrics_exist {
        lines.push("-".repeat(80));
        lines.push("Metrics:".to_string());
        lines.push("-".repeat(80));
        for check_result in &check_results {
            let metrics = check_result.getattr("metrics")?;
            if !metrics.is_truthy()? {
                continue;
            }
            lines.push(format!("{}:", get_str(check_result, "check_name")?));
            for (key, value) in metrics.cast::<PyDict>()?.iter() {
                let key = py_str(&key)?;
                if value.is_instance_of::<pyo3::types::PyFloat>() {
                    lines.push(format!(
                        "  {key}: {}",
                        py_float_fmt_3(value.extract::<f64>()?)
                    ));
                } else {
                    lines.push(format!("  {key}: {}", py_str(&value)?));
                }
            }
            lines.push(String::new());
        }
    }

    lines.push("=".repeat(80));
    Ok(lines.join("\n"))
}

/// `temper_placer.report.formatter.format_text` — byte-identical text.
#[pyfunction]
pub fn report_format_text(result: &Bound<'_, PyAny>) -> PyResult<String> {
    temper_py_bridge_catch(|| format_text_impl(result))
}

fn format_json_data_impl<'py>(
    py: Python<'py>,
    result: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let check_results = iter_items(&result.getattr("check_results")?)?;
    let passed_checks = check_results
        .iter()
        .filter(|r| {
            r.getattr("passed")
                .map(|p| p.is_truthy().unwrap_or(false))
                .unwrap_or(false)
        })
        .count();
    let failed_checks = check_results.len() - passed_checks;
    let total_issues = iter_items(&result.getattr("all_issues")?)?.len();

    let data = PyDict::new(py);
    data.set_item("passed", result.getattr("passed")?.is_truthy()?)?;
    data.set_item("total_checks", check_results.len())?;
    data.set_item("passed_checks", passed_checks)?;
    data.set_item("failed_checks", failed_checks)?;
    data.set_item("total_issues", total_issues)?;
    data.set_item("runtime_ms", get_f64(result, "total_elapsed_ms")?)?;

    let checks = PyList::empty(py);
    for check_result in &check_results {
        let check_data = PyDict::new(py);
        check_data.set_item("name", get_str(check_result, "check_name")?)?;
        check_data.set_item("passed", check_result.getattr("passed")?.is_truthy()?)?;
        check_data.set_item("elapsed_ms", get_f64(check_result, "elapsed_ms")?)?;
        let issues = iter_items(&check_result.getattr("issues")?)?;
        check_data.set_item("issue_count", issues.len())?;
        let issues_list = PyList::empty(py);
        for issue in &issues {
            let issue_data = PyDict::new(py);
            issue_data.set_item("severity", severity_name(issue)?)?;
            issue_data.set_item("code", get_str(issue, "code")?)?;
            issue_data.set_item("message", get_str(issue, "message")?)?;
            issue_data.set_item("category", get_str(issue, "category")?)?;
            issue_data.set_item("affected_items", issue.getattr("affected_items")?)?;
            let location = issue.getattr("location")?;
            if !location.is_none() {
                let loc = PyDict::new(py);
                loc.set_item("x", get_f64(&location, "x")?)?;
                loc.set_item("y", get_f64(&location, "y")?)?;
                loc.set_item("layer", location.getattr("layer")?)?;
                issue_data.set_item("location", loc)?;
            }
            let details = issue.getattr("details")?;
            if !details.is_empty()? {
                issue_data.set_item("details", details)?;
            }
            issues_list.append(issue_data)?;
        }
        check_data.set_item("issues", issues_list)?;
        check_data.set_item("metrics", check_result.getattr("metrics")?)?;
        checks.append(check_data)?;
    }
    data.set_item("checks", checks)?;
    Ok(data)
}

/// `format_json`'s data half — the shim renders it with `json.dumps(indent=2)`.
#[pyfunction]
pub fn report_format_json_data(py: Python<'_>, result: &Bound<'_, PyAny>) -> PyResult<Py<PyDict>> {
    temper_py_bridge_catch(|| format_json_data_impl(py, result).map(|d| d.unbind()))
}

fn format_html_impl(result: &Bound<'_, PyAny>, placement_name: &str) -> PyResult<String> {
    let passed = result.getattr("passed")?.is_truthy()?;
    let status_color = if passed { "#28a745" } else { "#dc3545" };
    let status_text = if passed { "PASS" } else { "FAIL" };

    let check_results = iter_items(&result.getattr("check_results")?)?;
    let passed_checks = check_results
        .iter()
        .filter(|r| {
            r.getattr("passed")
                .map(|p| p.is_truthy().unwrap_or(false))
                .unwrap_or(false)
        })
        .count();
    let failed_checks = check_results.len() - passed_checks;

    let mut severity_counts = [0usize; 4]; // CRITICAL, ERROR, WARNING, INFO
    for r in &check_results {
        for issue in iter_items(&r.getattr("issues")?)? {
            match severity_name(&issue)?.as_str() {
                "CRITICAL" => severity_counts[0] += 1,
                "ERROR" => severity_counts[1] += 1,
                "WARNING" => severity_counts[2] += 1,
                "INFO" => severity_counts[3] += 1,
                _ => {}
            }
        }
    }

    let mut check_rows: Vec<String> = Vec::new();
    for check_result in &check_results {
        let cr_passed = check_result.getattr("passed")?.is_truthy()?;
        let status_icon = if cr_passed { "\u{2713}" } else { "\u{2717}" };
        let row_class = if cr_passed {
            "table-success"
        } else {
            "table-danger"
        };

        let mut issue_details = String::new();
        let issues = iter_items(&check_result.getattr("issues")?)?;
        if !issues.is_empty() {
            let mut issue_list = vec!["<ul>".to_string()];
            for issue in &issues {
                let sev_name = severity_name(issue)?;
                let badge = severity_to_bootstrap(&sev_name);
                let code = get_str(issue, "code")?;
                let message = get_str(issue, "message")?;
                issue_list.push(format!(
                    "<li><span class=\"badge badge-{badge}\">{sev_name}</span> {code}: {message}</li>"
                ));
            }
            issue_list.push("</ul>".to_string());
            issue_details = issue_list.join("");
        }

        let elapsed = py_float_fmt_1(get_f64(check_result, "elapsed_ms")?);
        let name = get_str(check_result, "check_name")?;
        let n_issues = issues.len();
        check_rows.push(format!(
            "<tr class=\"{row_class}\"><td>{status_icon}</td><td>{name}</td><td>{n_issues}</td><td>{elapsed}ms</td><td>{issue_details}</td></tr>"
        ));
    }

    let all_issues_count = iter_items(&result.getattr("all_issues")?)?.len();
    let total_elapsed = py_float_fmt_1(get_f64(result, "total_elapsed_ms")?);

    let mut out = String::from(
        "\n<!DOCTYPE html>\n<html>\n<head>\n    <meta charset=\"utf-8\">\n    <title>temper-drc Check Report</title>\n    <link rel=\"stylesheet\" href=\"https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css\">\n    <style>\n        body { padding: 20px; }\n        .summary-card { margin-bottom: 20px; }\n        .metric-badge { font-size: 2rem; margin: 10px 0; }\n    </style>\n</head>\n<body>\n    <div class=\"container-fluid\">\n        <h1>temper-drc Check Report</h1>\n        <p class=\"text-muted\">Placement: ",
    );
    out.push_str(placement_name);
    out.push_str("</p>\n\n        <div class=\"row summary-card\">\n            <div class=\"col-md-3\">\n                <div class=\"card text-center\">\n                    <div class=\"card-body\">\n                        <h5 class=\"card-title\">Status</h5>\n                        <div class=\"metric-badge\" style=\"color: ");
    out.push_str(status_color);
    out.push_str(";\">");
    out.push_str(status_text);
    out.push_str("</div>\n                    </div>\n                </div>\n            </div>\n            <div class=\"col-md-3\">\n                <div class=\"card text-center\">\n                    <div class=\"card-body\">\n                        <h5 class=\"card-title\">Checks</h5>\n                        <div class=\"metric-badge\">");
    out.push_str(&format!(
        "{passed_checks}/{total_checks}",
        total_checks = check_results.len()
    ));
    out.push_str("</div>\n                        <p class=\"text-muted\">");
    out.push_str(&format!("{failed_checks} failed"));
    out.push_str("</p>\n                    </div>\n                </div>\n            </div>\n            <div class=\"col-md-3\">\n                <div class=\"card text-center\">\n                    <div class=\"card-body\">\n                        <h5 class=\"card-title\">Issues</h5>\n                        <div class=\"metric-badge\">");
    out.push_str(&format!("{all_issues_count}"));
    out.push_str("</div>\n                        <p class=\"text-muted\">\n                            <span class=\"badge badge-danger\">");
    out.push_str(&format!("{} Critical", severity_counts[0]));
    out.push_str("</span>\n                            <span class=\"badge badge-warning\">");
    out.push_str(&format!("{} Error", severity_counts[1]));
    out.push_str("</span>\n                            <span class=\"badge badge-info\">");
    out.push_str(&format!("{} Warning", severity_counts[2]));
    out.push_str("</span>\n                        </p>\n                    </div>\n                </div>\n            </div>\n            <div class=\"col-md-3\">\n                <div class=\"card text-center\">\n                    <div class=\"card-body\">\n                        <h5 class=\"card-title\">Runtime</h5>\n                        <div class=\"metric-badge\">");
    out.push_str(&total_elapsed);
    out.push_str("ms</div>\n                    </div>\n                </div>\n            </div>\n        </div>\n\n        <h2>Check Results</h2>\n        <table class=\"table table-striped\">\n            <thead>\n                <tr>\n                    <th>Status</th>\n                    <th>Check</th>\n                    <th>Issues</th>\n                    <th>Time</th>\n                    <th>Details</th>\n                </tr>\n            </thead>\n            <tbody>\n                ");
    out.push_str(&check_rows.join(""));
    out.push_str("\n            </tbody>\n        </table>\n\n        <hr>\n        <footer class=\"text-muted\">\n            <p>Generated by temper-drc</p>\n        </footer>\n    </div>\n</body>\n</html>\n");
    Ok(out)
}

/// `temper_placer.report.formatter.format_html` — byte-identical HTML.
#[pyfunction]
#[pyo3(signature = (result, placement_name))]
pub fn report_format_html(result: &Bound<'_, PyAny>, placement_name: &str) -> PyResult<String> {
    temper_py_bridge_catch(|| format_html_impl(result, placement_name))
}

fn severity_to_bootstrap(sev_name: &str) -> &'static str {
    match sev_name {
        "CRITICAL" => "danger",
        "ERROR" => "warning",
        "WARNING" => "info",
        "INFO" => "secondary",
        _ => "secondary",
    }
}

// ---------------------------------------------------------------------------
// generator.py
// ---------------------------------------------------------------------------

/// Python `dict.get(key, default)` where the default is lazily produced.
fn dict_get<'py>(
    dict: &Bound<'py, PyDict>,
    key: &str,
    default: impl FnOnce() -> PyResult<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    if let Ok(Some(v)) = dict.get_item(key) {
        return Ok(v);
    }
    default()
}

fn calculate_benchmark_result_impl<'py>(
    py: Python<'py>,
    name: &str,
    opt_result: &Bound<'py, PyAny>,
    baseline: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    // human_p = baseline.get("human_placement", {})
    // human_metrics = human_p.get("metrics", baseline.get("human_metrics", {}))
    let baseline_dict = baseline.cast::<PyDict>()?;
    let human_p = dict_get(baseline_dict, "human_placement", || {
        Ok(PyDict::new(py).into_any())
    })?;
    let human_metrics = if human_p.is_instance_of::<PyDict>() {
        let hp = human_p.cast::<PyDict>()?;
        dict_get(hp, "metrics", || {
            dict_get(baseline_dict, "human_metrics", || {
                Ok(PyDict::new(py).into_any())
            })
        })?
    } else {
        // baseline["human_placement"] present but not a dict: `.get` would
        // AttributeError on a non-dict; preserve the same failure by
        // attempting getattr('get').
        human_p.call_method1("get", ("metrics",))? // noqa — mirrors Python
    };

    let human_metrics_dict = human_metrics.cast::<PyDict>()?;
    // human_wl = human_metrics.get("total_wirelength_mm", human_metrics.get("total_hpwl_mm", 0.0))
    let human_wl_obj = dict_get(human_metrics_dict, "total_wirelength_mm", || {
        dict_get(human_metrics_dict, "total_hpwl_mm", || {
            Ok(0.0_f64.into_pyobject(py)?.into_any())
        })
    })?;
    let human_wl = to_f64(&human_wl_obj)?;

    // final_metrics = opt_result.history[-1]
    let history = iter_items(&opt_result.getattr("history")?)?;
    let last = history
        .last()
        .ok_or_else(|| pyo3::exceptions::PyIndexError::new_err("list index out of range"))?;
    let loss_breakdown_obj = last.getattr("loss_breakdown")?;
    let loss_breakdown = loss_breakdown_obj.cast::<PyDict>()?;

    let get_loss = |key: &str| -> PyResult<f64> {
        let v = dict_get(loss_breakdown, key, || {
            Ok(0.0_f64.into_pyobject(py)?.into_any())
        })?;
        to_f64(&v)
    };

    let opt_wl = get_loss("wirelength")?;
    let wl_ratio = if human_wl > 0.0 {
        opt_wl / human_wl
    } else {
        1.0
    };

    let overlap_val = get_loss("overlap")?;
    let overlap_score = if overlap_val < 1.0 {
        1.0
    } else {
        (1.0 - (overlap_val / 100.0)).max(0.0)
    };
    let boundary_val = get_loss("boundary")?;
    let boundary_score = if boundary_val < 1.0 {
        1.0
    } else {
        (1.0 - (boundary_val / 100.0)).max(0.0)
    };
    let thermal_val = get_loss("thermal")?;
    let thermal_score = if thermal_val > 0.0 {
        1.0 / (1.0 + thermal_val / 10.0)
    } else {
        1.0
    };

    let compactness_obj = dict_get(human_metrics_dict, "compactness_score", || {
        dict_get(human_metrics_dict, "density", || {
            Ok(0.5_f64.into_pyobject(py)?.into_any())
        })
    })?;
    let compactness_score = to_f64(&compactness_obj)?;

    let overall = if overlap_score < 0.9 || boundary_score < 0.9 {
        // Python's min() keeps the first arg unless the second is strictly
        // less — order-sensitive around NaN, unlike f64::min.
        py_min(overlap_score, boundary_score) * 0.5
    } else {
        0.4 * (1.0 / (wl_ratio.max(0.5))) + 0.3 * thermal_score + 0.3 * compactness_score
    };

    let mut violations: Vec<String> = Vec::new();
    if overlap_val > 10.0 {
        violations.push(format!(
            "Overlap too high ({})",
            py_float_fmt_1(overlap_val)
        ));
    }
    if boundary_val > 10.0 {
        violations.push(format!(
            "Boundary violation ({})",
            py_float_fmt_1(boundary_val)
        ));
    }

    let status = if !violations.is_empty() {
        "FAIL"
    } else if wl_ratio < 0.95 {
        "BETTER"
    } else {
        "PASS"
    };

    let out = PyDict::new(py);
    out.set_item("name", name)?;
    out.set_item("drc_errors", 0)?;
    out.set_item("wirelength_ratio", wl_ratio)?;
    out.set_item("overlap_score", overlap_score)?;
    out.set_item("boundary_score", boundary_score)?;
    out.set_item("thermal_score", thermal_score)?;
    out.set_item("compactness_score", compactness_score)?;
    out.set_item("overall_score", overall)?;
    out.set_item("status", status)?;
    out.set_item("violations", violations)?;
    Ok(out)
}

/// `calculate_benchmark_result`'s numeric kernel — returns the
/// `BenchmarkResult` field payload; the shim constructs the dataclass.
#[pyfunction]
#[pyo3(signature = (name, opt_result, baseline))]
pub fn report_calculate_benchmark_result(
    py: Python<'_>,
    name: &str,
    opt_result: &Bound<'_, PyAny>,
    baseline: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    temper_py_bridge_catch(|| {
        calculate_benchmark_result_impl(py, name, opt_result, baseline).map(|d| d.unbind())
    })
}

fn benchmark_json_data_impl<'py>(
    py: Python<'py>,
    summary: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let data = PyDict::new(py);
    data.set_item("timestamp", get_str(summary, "timestamp")?)?;

    let s = PyDict::new(py);
    let total_pcbs: i64 = summary.getattr("total_pcbs")?.extract()?;
    let passed: i64 = summary.getattr("passed")?.extract()?;
    let failed: i64 = summary.getattr("failed")?.extract()?;
    let better_than_human: i64 = summary.getattr("better_than_human")?.extract()?;
    s.set_item("total_pcbs", total_pcbs)?;
    s.set_item("passed", passed)?;
    s.set_item("failed", failed)?;
    s.set_item("better_than_human", better_than_human)?;
    // pass_rate = passed / total if total > 0 else 0  (int 0 — leaf type!)
    if total_pcbs > 0 {
        s.set_item("pass_rate", passed as f64 / total_pcbs as f64)?;
    } else {
        s.set_item("pass_rate", 0)?;
    }
    data.set_item("summary", s)?;

    let results = PyList::empty(py);
    for r in iter_items(&summary.getattr("results")?)? {
        let rd = PyDict::new(py);
        rd.set_item("name", get_str(&r, "name")?)?;
        rd.set_item("drc_errors", r.getattr("drc_errors")?.extract::<i64>()?)?;
        rd.set_item("wirelength_ratio", get_f64(&r, "wirelength_ratio")?)?;
        rd.set_item("thermal_score", get_f64(&r, "thermal_score")?)?;
        rd.set_item("compactness_score", get_f64(&r, "compactness_score")?)?;
        rd.set_item("overall_score", get_f64(&r, "overall_score")?)?;
        rd.set_item("status", get_str(&r, "status")?)?;
        rd.set_item("violations", r.getattr("violations")?)?;
        results.append(rd)?;
    }
    data.set_item("results", results)?;
    Ok(data)
}

/// `generate_json_report`'s data half — the shim writes it with
/// `json.dump(data, f, indent=2)`.
#[pyfunction]
pub fn report_benchmark_json_data(
    py: Python<'_>,
    summary: &Bound<'_, PyAny>,
) -> PyResult<Py<PyDict>> {
    temper_py_bridge_catch(|| benchmark_json_data_impl(py, summary).map(|d| d.unbind()))
}

// ---------------------------------------------------------------------------
// summary.py
// ---------------------------------------------------------------------------

fn extract_key_metrics_impl<'py>(
    py: Python<'py>,
    result: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let out = PyList::empty(py);
    for check_result in iter_items(&result.getattr("check_results")?)? {
        let metrics = check_result.getattr("metrics")?;
        if !metrics.is_truthy()? {
            continue;
        }
        let md = metrics.cast::<PyDict>()?;
        for (name, key) in [
            ("Minimum Clearance", "min_clearance_mm"),
            ("Component Overlaps", "overlap_count"),
            ("Max Loop Area (mm\u{b2})", "max_loop_area_mm2"),
            ("Ground Discontinuities", "ground_discontinuities"),
            ("Floating Pins", "floating_pins"),
        ] {
            if let Ok(Some(v)) = md.get_item(key) {
                let name_obj: Bound<'py, PyAny> = name.into_pyobject(py)?.into_any();
                let tup = PyTuple::new(py, [name_obj, v])?;
                out.append(tup)?;
            }
        }
    }
    Ok(out)
}

/// `summary._extract_key_metrics` — list of (label, value) tuples.
#[pyfunction]
pub fn report_extract_key_metrics(
    py: Python<'_>,
    result: &Bound<'_, PyAny>,
) -> PyResult<Py<PyList>> {
    temper_py_bridge_catch(|| extract_key_metrics_impl(py, result).map(|l| l.unbind()))
}

fn generate_summary_impl<'py>(
    py: Python<'py>,
    result: &Bound<'py, PyAny>,
    placement: &Bound<'py, PyAny>,
) -> PyResult<String> {
    let mut lines: Vec<String> = vec![
        "=".repeat(60),
        "temper-drc Summary".to_string(),
        "=".repeat(60),
        String::new(),
    ];

    let passed = result.getattr("passed")?.is_truthy()?;
    lines.push(format!(
        "Overall Status: {}",
        if passed {
            "\u{2713} PASS"
        } else {
            "\u{2717} FAIL"
        }
    ));
    lines.push(String::new());

    lines.push("Statistics:".to_string());
    let components = placement.getattr("components")?;
    lines.push(format!("  Components: {}", components.len()?));
    let nets = placement.getattr("nets")?;
    lines.push(format!("  Nets: {}", nets.len()?));
    let zones = placement.getattr("zones")?;
    lines.push(format!("  Zones: {}", zones.len()?));
    // Python renders int 100 as "100" and float 100.0 as "100.0" — use
    // Python's own str() for the board dims (int-vs-float rendering pin).
    let bw = py_str(&placement.getattr("board_width")?)?;
    let bh = py_str(&placement.getattr("board_height")?)?;
    lines.push(format!("  Board Size: {bw}mm \u{d7} {bh}mm"));
    lines.push(String::new());

    let check_results = iter_items(&result.getattr("check_results")?)?;
    let total_checks = check_results.len();
    let passed_checks = check_results
        .iter()
        .filter(|r| {
            r.getattr("passed")
                .map(|p| p.is_truthy().unwrap_or(false))
                .unwrap_or(false)
        })
        .count();
    let failed_checks = total_checks - passed_checks;

    lines.push("Check Summary:".to_string());
    lines.push(format!("  Total Checks: {total_checks}"));
    lines.push(format!("  Passed: {passed_checks}"));
    lines.push(format!("  Failed: {failed_checks}"));
    lines.push(format!(
        "  Runtime: {}ms",
        py_float_fmt_1(get_f64(result, "total_elapsed_ms")?)
    ));
    lines.push(String::new());

    // issues_by_category, insertion order then sorted ascending by key
    let mut by_category: Vec<(String, usize)> = Vec::new();
    for r in &check_results {
        for issue in iter_items(&r.getattr("issues")?)? {
            let category = get_str(&issue, "category")?;
            if let Some(entry) = by_category.iter_mut().find(|(k, _)| *k == category) {
                entry.1 += 1;
            } else {
                by_category.push((category, 1));
            }
        }
    }
    if !by_category.is_empty() {
        lines.push("Issues by Category:".to_string());
        by_category.sort_by(|a, b| a.0.cmp(&b.0));
        for (category, count) in &by_category {
            lines.push(format!("  {}: {count}", category.to_uppercase()));
        }
        lines.push(String::new());
    }

    let key_metrics = extract_key_metrics_impl(py, result)?;
    if !key_metrics.is_empty() {
        lines.push("Key Metrics:".to_string());
        for item in key_metrics.iter() {
            let tup = item.cast::<PyTuple>()?;
            let name = py_str(&tup.get_item(0)?)?;
            let value = tup.get_item(1)?;
            if value.is_instance_of::<pyo3::types::PyFloat>() {
                lines.push(format!(
                    "  {name}: {}",
                    py_float_fmt_3(value.extract::<f64>()?)
                ));
            } else {
                lines.push(format!("  {name}: {}", py_str(&value)?));
            }
        }
        lines.push(String::new());
    }

    let all_issues = iter_items(&result.getattr("all_issues")?)?;
    if !all_issues.is_empty() {
        let mut critical_count = 0usize;
        let mut error_count = 0usize;
        let mut warning_count = 0usize;
        for issue in &all_issues {
            match severity_name(issue)?.as_str() {
                "CRITICAL" => critical_count += 1,
                "ERROR" => error_count += 1,
                "WARNING" => warning_count += 1,
                _ => {}
            }
        }

        lines.push("Issue Severity Breakdown:".to_string());
        if critical_count > 0 {
            lines.push(format!("  CRITICAL: {critical_count}"));
        }
        if error_count > 0 {
            lines.push(format!("  ERROR: {error_count}"));
        }
        if warning_count > 0 {
            lines.push(format!("  WARNING: {warning_count}"));
        }
        lines.push(String::new());

        // top_issues: stable sort by (is INFO, is WARNING, is ERROR, is
        // CRITICAL) — ascending rank CRITICAL < ERROR < WARNING < INFO —
        // then first 5.
        let mut ranked: Vec<(u8, &Bound<'_, PyAny>)> = all_issues
            .iter()
            .map(|issue| {
                let rank = match severity_name(issue).unwrap_or_default().as_str() {
                    "CRITICAL" => 0u8,
                    "ERROR" => 1,
                    "WARNING" => 2,
                    "INFO" => 3,
                    _ => 3,
                };
                (rank, issue)
            })
            .collect();
        ranked.sort_by(|a, b| a.0.cmp(&b.0));
        let top_issues = ranked.iter().take(5);

        if !ranked.is_empty() {
            lines.push("Top Issues:".to_string());
            for (_, issue) in top_issues {
                let sev = severity_name(issue)?;
                let code = get_str(issue, "code")?;
                let message = get_str(issue, "message")?;
                lines.push(format!("  [{sev}] {code}: {message}"));
            }
            lines.push(String::new());
        }
    }

    lines.push("=".repeat(60));
    Ok(lines.join("\n"))
}

/// `temper_placer.report.summary.generate_summary` — byte-identical text.
#[pyfunction]
pub fn report_generate_summary(
    py: Python<'_>,
    result: &Bound<'_, PyAny>,
    placement: &Bound<'_, PyAny>,
) -> PyResult<String> {
    temper_py_bridge_catch(|| generate_summary_impl(py, result, placement))
}

// ---------------------------------------------------------------------------
// catch_unwind seam (R1g: no panic across the pyo3 boundary)
// ---------------------------------------------------------------------------

/// Wrap a closure so a Rust panic becomes a Python RuntimeError instead of
/// unwinding across the FFI boundary. This crate does not depend on
/// temper-py-bridge (pure-core split), so the seam is local.
fn temper_py_bridge_catch<T>(f: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(res) => res,
        Err(panic) => Err(pyo3::exceptions::PyRuntimeError::new_err(format!(
            "panicked in temper-io-types: {}",
            panic_message(&panic)
        ))),
    }
}

fn panic_message(panic: &Box<dyn std::any::Any + Send>) -> String {
    if let Some(s) = panic.downcast_ref::<&str>() {
        (*s).to_string()
    } else if let Some(s) = panic.downcast_ref::<String>() {
        s.clone()
    } else {
        "unknown panic payload".to_string()
    }
}
