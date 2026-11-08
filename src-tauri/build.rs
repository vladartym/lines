use std::process::Command;

fn main() {
    allow_server();

    // contacts.m reads the contacts, on the Mac and on the iPhone. -fmodules links the Contacts framework by itself,
    // also in the Xcode link of the iPhone app.
    println!("cargo:rerun-if-changed=contacts.m");
    cc::Build::new().file("contacts.m").flag("-fobjc-arc").flag("-fmodules").flag("-Wno-unused-parameter").compile("contacts");
    println!("cargo:rustc-link-lib=framework=Contacts");

    // The SwiftUI parts of the Mac app (mac/), as a static library. The iPhone app gets its Swift from the Xcode
    // project instead (gen/apple/Sources/lines).
    let target = std::env::var("TARGET").unwrap();
    if target.ends_with("apple-darwin") {
        println!("cargo:rerun-if-changed=mac");
        let out = std::env::var("OUT_DIR").unwrap();
        let arch = if target.starts_with("x86_64") { "x86_64" } else { "arm64" };
        let mut sources: Vec<String> = std::fs::read_dir("mac")
            .expect("the folder mac/")
            .filter_map(|e| e.ok()?.path().to_str().map(String::from))
            .filter(|p| p.ends_with(".swift"))
            .collect();
        sources.sort();
        // macOS 26 is the first with Liquid Glass. Info.plist sets the same LSMinimumSystemVersion.
        let ok = Command::new("xcrun")
            .args(["swiftc", "-parse-as-library", "-emit-library", "-static", "-module-name", "LinesMac", "-O"])
            .args(["-target", &format!("{arch}-apple-macos26.0")])
            .args(&sources)
            .args(["-o", &format!("{out}/liblinesmac.a")])
            .status()
            .is_ok_and(|s| s.success());
        assert!(ok, "swiftc could not compile mac/");
        println!("cargo:rustc-link-search=native={out}");
        println!("cargo:rustc-link-lib=static=linesmac");
        // The Swift runtime is in macOS. The linker finds it in the SDK, and the toolchain has the rest.
        let sdk = output("xcrun", &["--sdk", "macosx", "--show-sdk-path"]);
        let developer = output("xcode-select", &["-p"]);
        println!("cargo:rustc-link-search=native={sdk}/usr/lib/swift");
        println!("cargo:rustc-link-search=native={developer}/Toolchains/XcodeDefault.xctoolchain/usr/lib/swift/macosx");
        println!("cargo:rustc-link-arg=-Wl,-rpath,/usr/lib/swift");
    }
    tauri_build::build()
}

// The app may fetch only from its own server. The address comes from VITE_SERVER_URL, in the environment or in ../.env,
// and goes into capabilities/default.json, which tauri_build reads. The file is not in git.
fn allow_server() {
    println!("cargo:rerun-if-env-changed=VITE_SERVER_URL");
    println!("cargo:rerun-if-changed=../.env");
    let url = std::env::var("VITE_SERVER_URL")
        .ok()
        .or_else(|| {
            std::fs::read_to_string("../.env").ok()?.lines().find_map(|line| {
                line.strip_prefix("VITE_SERVER_URL=").map(|v| v.trim().trim_matches('"').to_string())
            })
        })
        .unwrap_or_default();
    let url = url.trim_end_matches('/');
    assert!(
        url.starts_with("https://") && !url.contains('"') && !url.contains('*'),
        "Set VITE_SERVER_URL in .env to the https address of your server, such as https://phone.example.com"
    );
    let capability = format!(
        r#"{{
  "$schema": "../gen/schemas/desktop-schema.json",
  "identifier": "default",
  "description": "The main window: the commands of the app, and requests to its server only. build.rs writes this file.",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "core:window:allow-start-dragging",
    {{ "identifier": "http:default", "allow": [{{ "url": "{url}/*" }}] }}
  ]
}}
"#
    );
    // Write only on a change, so cargo does not run this script again at each build.
    if std::fs::read_to_string("capabilities/default.json").ok().as_deref() != Some(capability.as_str()) {
        std::fs::write("capabilities/default.json", capability).expect("capabilities/default.json");
    }
}

fn output(program: &str, args: &[&str]) -> String {
    let out = Command::new(program).args(args).output().expect(program);
    String::from_utf8(out.stdout).unwrap().trim().to_string()
}
