use std::process::Command;

fn main() {
    // Detect Python library directory for linking.
    // On Conda macOS and some Linux distributions, `python3-config --ldflags`
    // must be queried with `--embed` to include the -lpythonXY flag.
    let python = std::env::var("PYO3_PYTHON")
        .unwrap_or_else(|_| "python3".into());
    if let Ok(output) = Command::new(&python)
        .args(["-c", "import sysconfig; print(sysconfig.get_config_var('LIBDIR'))"])
        .output()
    {
        let lib_dir = String::from_utf8_lossy(&output.stdout).trim().to_string();
        if !lib_dir.is_empty() {
            println!("cargo:rustc-link-search=native={}", lib_dir);
        }
    }
    println!("cargo:rustc-link-lib=python3.12");
}
