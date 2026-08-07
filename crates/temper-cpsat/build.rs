//! Build the C++ shim and generate the CP-SAT protobuf structs.
//!
//! `cp_model_fds.bin` is a FileDescriptorSet extracted from the installed
//! ortools wheel (`tools/measurements/ortools_ffi_spike.py` regenerates it).
//! Carrying the descriptor set rather than a `.proto` is deliberate: OR-Tools
//! ships no `.proto` files in either the wheel or the brew bottle, and this
//! keeps the build free of an OR-Tools source checkout.
use std::path::PathBuf;

fn main() {
    // Read at RUNTIME, not via env!(): a compile-time constant bakes in the
    // path the build script was first compiled at, which breaks the moment the
    // crate moves directory.
    let manifest = std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR");
    let fds_path = PathBuf::from(manifest).join("cp_model_fds.bin");
    println!("cargo:rerun-if-changed={}", fds_path.display());
    println!("cargo:rerun-if-changed=src/shim.cc");

    let bytes = std::fs::read(&fds_path).expect("cp_model_fds.bin");
    let fds = <prost_types::FileDescriptorSet as prost::Message>::decode(&bytes[..])
        .expect("decode FileDescriptorSet");
    prost_build::Config::new().compile_fds(fds).expect("compile_fds");

    // OR_PROTO_DLL/OR_DLL are visibility macros the OR-Tools CMake build
    // defines; on non-Windows they are empty, and the shipped headers do not
    // define them themselves.
    let prefix = std::env::var("ORTOOLS_PREFIX").unwrap_or_else(|_| "/opt/homebrew".into());
    cc::Build::new()
        .cpp(true)
        .std("c++17")
        .file("src/shim.cc")
        .include(format!("{prefix}/include"))
        .define("OR_PROTO_DLL", "")
        .define("OR_DLL", "")
        .compile("temper_cpsat_shim");

    println!("cargo:rustc-link-search=native={prefix}/lib");
    println!("cargo:rustc-link-lib=dylib=ortools");
    println!("cargo:rustc-link-lib=dylib=protobuf");
}
