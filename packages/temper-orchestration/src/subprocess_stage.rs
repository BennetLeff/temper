// Option-E subprocess stage (2026-08-21): a `Stage<NativeBoardState>` whose
// `run` shells the not-yet-native compute out to a Python subprocess.
//
// The wire contract is `state_ser.rs`'s JSON codec: `native_to_json(state)`
// goes in on stdin, the subprocess materializes a Python
// `deterministic.state.BoardState`, runs one
// `temper_orchestration.run_<stage>` pyfunction, and prints the mutated
// state; `native_from_json` decodes it and REPLACES the threaded state.
//
// UNGATED (`--no-default-features` must build this): pure
// `std::process::Command` + serde, no pyo3. The wasm tier does not compile
// process spawning, but nothing here pulls it in unless instantiated.
//
// Error discipline: every failure mode — codec error, spawn failure,
// non-zero exit, stderr content — becomes a fatal `StageError` naming the
// stage and carrying the subprocess's stderr tail, never a silent pass-
// through of stale state.

use std::borrow::Cow;
use std::io::Write as _;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use crate::board_state::NativeBoardState;
use crate::stage::{Stage, StageError, StageErrorKind};
use crate::state_ser::{native_from_json, native_to_json};

const STAGE: &str = "subprocess_stage";

/// How many bytes of a failed subprocess's stderr to carry into the
/// [`StageError`] message (stderr can be arbitrarily large; the driver's
/// per-stage report needs the cause, not the whole log).
const STDERR_TAIL_BYTES: usize = 2000;

fn err(message: String) -> StageError {
    StageError::new(STAGE, message, StageErrorKind::Fatal)
}

/// One pipeline stage executed by a Python subprocess.
///
/// The Rust CLI driver (`crates/temper-cli` `pipeline-run`) builds one of
/// these per entry of `drc_aware_stage_order()`; RUST owns the loop, Python
/// executes the leaf compute until each stage is ported native.
#[derive(Debug, Clone)]
pub struct SubprocessStage {
    /// The pipeline stage name (passed as `--stage`; selects the
    /// `run_<name>` pyfunction on the Python side).
    pub stage_name: String,
    /// Python interpreter to spawn (the repo venv's python when present).
    pub python_bin: PathBuf,
    /// Path to `scripts/_stage_subprocess.py`.
    pub script_path: PathBuf,
}

impl SubprocessStage {
    pub fn new(stage_name: impl Into<String>, python_bin: impl Into<PathBuf>, script_path: impl Into<PathBuf>) -> Self {
        Self {
            stage_name: stage_name.into(),
            python_bin: python_bin.into(),
            script_path: script_path.into(),
        }
    }

    fn script_arg(&self) -> Cow<'_, str> {
        self.script_path.as_os_str().to_string_lossy()
    }
}

impl Stage<NativeBoardState> for SubprocessStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Owned(format!("{} [py-subproc]", self.stage_name))
    }

    fn run(&self, state: NativeBoardState) -> Result<NativeBoardState, StageError> {
        let input = native_to_json(&state)?;

        let mut child = Command::new(&self.python_bin)
            .arg(self.script_arg().into_owned())
            .arg("--stage")
            .arg(&self.stage_name)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| {
                err(format!(
                    "spawning {} --stage {}: {e}",
                    self.python_bin.display(),
                    self.stage_name
                ))
            })?;

        // Write stdin from a thread: if the subprocess writes more stdout
        // than the pipe buffer while we are still writing stdin, a
        // single-threaded write-then-read deadlocks both processes.
        let mut stdin = child.stdin.take().ok_or_else(|| err("child stdin unavailable".to_string()))?;
        let payload = input.clone();
        let writer = std::thread::spawn(move || {
            // A closed-stdin child (early exit) makes this write fail —
            // that is fine, the exit-status check below reports it.
            let _ = stdin.write_all(payload.as_bytes());
            let _ = stdin.flush();
            drop(stdin);
        });

        let output = child
            .wait_with_output()
            .map_err(|e| err(format!("waiting for {} subprocess: {e}", self.stage_name)))?;
        let _ = writer.join();

        if !output.status.success() {
            let stderr_tail = stderr_tail(&output.stderr);
            return Err(err(format!(
                "{} stage failed (exit {}): {stderr_tail}",
                self.stage_name,
                output.status.code().map(|c| c.to_string()).unwrap_or_else(|| "signal".to_string()),
            )));
        }

        let stdout = String::from_utf8(output.stdout).map_err(|e| {
            err(format!("{} stage printed non-UTF-8 stdout: {e}", self.stage_name))
        })?;
        let decoded = native_from_json(stdout.trim())?;
        Ok(decoded)
    }
}

fn stderr_tail(bytes: &[u8]) -> String {
    let text = String::from_utf8_lossy(bytes);
    let trimmed = text.trim();
    if trimmed.len() <= STDERR_TAIL_BYTES {
        return trimmed.to_string();
    }
    let start = trimmed.len() - STDERR_TAIL_BYTES;
    // Split at a char boundary (a byte offset mid-codepoint is invalid).
    let start = (start..trimmed.len())
        .find(|i| trimmed.is_char_boundary(*i))
        .unwrap_or(trimmed.len());
    format!("...{}", &trimmed[start..])
}

// ---------------------------------------------------------------------------
// Tests — spawn real /bin/sh scripts (no interpreter dependency)
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    use std::collections::HashSet;

    use crate::board_state::SlotId;

    /// A fake "interpreter": /bin/sh running an inline-script file. The
    /// stage's spawn shape (`BIN SCRIPT --stage NAME`) is exercised exactly
    /// as production uses it.
    fn sh_stage(name: &str, script_body: &str) -> (SubprocessStage, tempdir::TempDir) {
        let dir = tempdir::TempDir::new("subprocess-stage-test").expect("tempdir");
        let script = dir.path().join("fake_stage.sh");
        std::fs::write(&script, script_body).expect("write script");
        let stage = SubprocessStage::new(name, "/bin/sh", &script);
        (stage, dir)
    }

    #[test]
    fn happy_path_decodes_the_mutated_state() {
        let (stage, _dir) = sh_stage(
            "net_ordering",
            "#!/bin/sh\ncat >/dev/null\nprintf '%s' '{\"schema\":1,\"net_order\":[\"Net_A\",\"GND\"],\"opaque\":{},\"typed\":{\"zones\":[{\"name\":\"z\",\"bounds\":[[{\"int\":0},{\"int\":0}],[{\"int\":1},{\"float\":1.5}]]}]}}'\n",
        );
        let out = stage.run(NativeBoardState::new()).unwrap();
        assert_eq!(out.net_order, vec!["Net_A".to_string(), "GND".to_string()]);
        let zones = out.zones.expect("zones present");
        let z = zones.iter().next().unwrap();
        assert_eq!(z.name, "z");
    }

    #[test]
    fn state_fields_reach_the_subprocess_stdin() {
        // The fake stage copies its stdin back through a Rust-visible
        // channel: write it to a known file, then emit a valid empty state.
        let dir = tempdir::TempDir::new("subprocess-stage-test").expect("tempdir");
        let echo_to = dir.path().join("stdin-capture.json");
        let script = dir.path().join("capture.sh");
        std::fs::write(
            &script,
            format!(
                "#!/bin/sh\ncat > {}\nprintf '%s' '{{\"schema\":1,\"net_order\":[],\"opaque\":{{}},\"typed\":{{}}}}'\n",
                echo_to.display()
            ),
        )
        .expect("write script");

        let mut state = NativeBoardState::new();
        let mut slots = HashSet::new();
        slots.insert(SlotId(1.5, 2.5));
        state.used_slots = Some(slots);

        let stage = SubprocessStage::new("slot_generation", "/bin/sh", &script);
        let out = stage.run(state).unwrap();
        assert!(out.used_slots.is_none(), "the decoded replacement state wins");

        let captured = std::fs::read_to_string(&echo_to).expect("captured stdin");
        assert!(captured.contains("\"used_slots\":[[1.5,2.5]]"), "captured: {captured}");
    }

    #[test]
    fn nonzero_exit_propagates_stderr_into_stage_error() {
        let (stage, _dir) = sh_stage(
            "component_assignment",
            "#!/bin/sh\necho 'boom: missing slot_spacing' >&2\nexit 3\n",
        );
        let e = stage.run(NativeBoardState::new()).unwrap_err();
        assert_eq!(e.kind, StageErrorKind::Fatal);
        assert!(e.message.contains("exit 3"), "message: {}", e.message);
        assert!(e.message.contains("missing slot_spacing"), "stderr must reach the error");
    }

    #[test]
    fn malformed_stdout_is_a_loud_error() {
        let (stage, _dir) = sh_stage("drc_validation", "#!/bin/sh\necho 'not json'\n");
        let e = stage.run(NativeBoardState::new()).unwrap_err();
        assert!(e.message.contains("state JSON"), "message: {}", e.message);
    }

    #[test]
    fn missing_interpreter_is_a_spawn_error() {
        let dir = tempdir::TempDir::new("subprocess-stage-test").expect("tempdir");
        let script = dir.path().join("stage.sh");
        std::fs::write(&script, "#!/bin/sh\ncat\n").expect("write script");
        let stage = SubprocessStage::new("zone_assignment", "/nonexistent/python", &script);
        let e = stage.run(NativeBoardState::new()).unwrap_err();
        assert!(e.message.contains("spawning"), "message: {}", e.message);
    }

    #[test]
    fn opaque_values_survive_the_round_trip_through_a_passthrough_script() {
        let (stage, _dir) = sh_stage("config_attach", "#!/bin/sh\ncat\n");
        let mut state = NativeBoardState::new();
        state.config = Some(Box::new(serde_json::json!({ "placer": { "k": 1 } })));
        let out = stage.run(state).unwrap();
        let cfg = out.config.as_ref().unwrap().downcast_ref::<serde_json::Value>().unwrap();
        assert_eq!(cfg["placer"]["k"], serde_json::json!(1));
    }

    #[test]
    fn non_value_opaque_fails_before_any_spawn() {
        let (stage, _dir) = sh_stage("config_attach", "#!/bin/sh\ncat\n");
        let mut state = NativeBoardState::new();
        state.board = Some(Box::new(42_u32));
        let e = stage.run(state).unwrap_err();
        assert!(e.message.contains("board"), "error names the field: {}", e.message);
    }

    /// Minimal scoped temp-dir helper (no tempfile dev-dependency).
    mod tempdir {
        use std::path::{Path, PathBuf};
        use std::sync::atomic::{AtomicU64, Ordering};

        static COUNTER: AtomicU64 = AtomicU64::new(0);

        pub(crate) struct TempDir(PathBuf);

        impl TempDir {
            pub(crate) fn new(prefix: &str) -> std::io::Result<Self> {
                let n = COUNTER.fetch_add(1, Ordering::Relaxed);
                let pid = std::process::id();
                let path = std::env::temp_dir().join(format!("{prefix}-{pid}-{n}"));
                std::fs::create_dir_all(&path)?;
                Ok(Self(path))
            }

            pub(crate) fn path(&self) -> &Path {
                &self.0
            }
        }

        impl Drop for TempDir {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
    }
}
