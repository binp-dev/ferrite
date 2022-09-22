use std::env;
use std::fs;
use std::path::Path;

fn main() {
    let src = Path::new(&env::var_os("FER_PROTO_DIR").unwrap()).join("rust/src/proto.rs");
    let dst = Path::new(&env::var_os("OUT_DIR").unwrap()).join("proto.rs");
    fs::copy(&src, &dst).unwrap();
    println!("cargo:rerun-if-changed=build.rs");
    println!("cargo:rerun-if-changed={}", src.display());
}