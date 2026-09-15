"""Arma un Swift SDK (artifactbundle) para arm64-apple-ios usando el SDK y los
resource dirs sacados del Xcode de la macVM, para poder usar
`swift build --swift-sdk arm64-apple-ios` desde Linux."""
import json, os, shutil

XC   = "/root/iospoc/xc/Toolchains/XcodeDefault.xctoolchain"
SDK  = "/root/iospoc/iossdk/iPhoneOS26.2.sdk"
PLAT = "/root/iospoc/xc/Platforms/iPhoneOS.platform/Developer"
DST  = "/root/.swiftpm/swift-sdks/darwin-ios.artifactbundle"
LD   = shutil.which("ld64.lld") or shutil.which("ld64.lld-18") or "/usr/bin/ld64.lld-18"

shutil.rmtree(DST, ignore_errors=True)
os.makedirs(os.path.join(DST, "darwin-ios"), exist_ok=True)

json.dump({
    "schemaVersion": "1.0",
    "artifacts": {
        "darwin-ios": {
            "type": "swiftSDK",
            "version": "0.0.1",
            "variants": [{"path": "darwin-ios", "supportedTriples": ["x86_64-unknown-linux-gnu"]}],
        }
    },
}, open(os.path.join(DST, "info.json"), "w"), indent=2)

common = [
    "-sdk", SDK,
    "-resource-dir", f"{XC}/usr/lib/swift",
    "-Xcc", "-resource-dir", "-Xcc", f"{XC}/usr/lib/clang/17",
    "-F", f"{PLAT}/Library/Frameworks",
]
json.dump({
    "schemaVersion": "1.0",
    "rootPath": None,
    "swiftCompiler": {"extraCLIOptions": common},
    "cCompiler":   {"extraCLIOptions": ["-isysroot", SDK, "-resource-dir", f"{XC}/usr/lib/clang/17"]},
    "cxxCompiler": {"extraCLIOptions": ["-isysroot", SDK, "-resource-dir", f"{XC}/usr/lib/clang/17"]},
    "linker": {"path": LD},
}, open(os.path.join(DST, "darwin-ios", "toolset.json"), "w"), indent=2)

json.dump({
    "schemaVersion": "4.0",
    "targetTriples": {
        "arm64-apple-ios": {
            "sdkRootPath": SDK,
            "toolsetPaths": ["toolset.json"],
        }
    },
}, open(os.path.join(DST, "darwin-ios", "swift-sdk.json"), "w"), indent=2)
print("Swift SDK bundle:", DST, "linker:", LD)
