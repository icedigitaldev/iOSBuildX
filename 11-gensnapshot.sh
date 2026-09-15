#!/bin/bash
# Compila un gen_snapshot para Linux x86_64 que genera AOT de iOS arm64.
#   bash 11-gensnapshot.sh [version_flutter]    → ./gen_snapshot-ios
set -euxo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
FLUTTER=${1:-$(grep -m1 '^FLUTTER=' "$HERE/app.env" | cut -d= -f2)}
W=${W:-/workspace/gensnapshot}
OUTBIN=${OUTBIN:-$PWD/gen_snapshot-ios}

REV=$(curl -fsSL "https://raw.githubusercontent.com/flutter/flutter/$FLUTTER/DEPS" \
  | awk -F"'" '$2 == "dart_revision" && !r {r = $4} END {print r}')
[ -n "$REV" ] || { echo "error: dart_revision not found for Flutter $FLUTTER"; exit 1; }

shallow() {
  [ "$(git -C "$1" rev-parse HEAD 2>/dev/null)" = "$3" ] && return
  rm -rf "$1" && mkdir -p "$1"
  git -C "$1" init -q && git -C "$1" fetch -q --depth 1 "$2" "$3" && git -C "$1" checkout -q FETCH_HEAD
}

mkdir -p "$W" && cd "$W"
[ -d depot_tools ] || git clone -q --depth 1 https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH=$W/depot_tools:$PATH DEPOT_TOOLS_UPDATE=0
shallow sdk https://dart.googlesource.com/sdk.git "$REV"

# dependencias git del DEPS y toolchain de CIPD
python3 - <<'PY'
g = {}
def Var(n): return g["vars"][n]
exec(open("sdk/DEPS").read(), {"Var": Var, "Str": str}, g)
deps = {k.split("/", 1)[1]: v for k, v in g["deps"].items()}
with open("git.list", "w") as f:
    for p, d in deps.items():
        if isinstance(d, dict):
            if d.get("dep_type") == "cipd" or "condition" in d:
                continue
            d = d["url"]
        url, rev = d.rsplit("@", 1)
        f.write(f"sdk/{p} {url} {rev}\n")
cipd = {"buildtools": "gn/gn/${platform}",
        "buildtools/linux-x64/clang": "fuchsia/third_party/clang/linux-amd64",
        "buildtools/ninja": "infra/3pp/tools/ninja/${platform}",
        "buildtools/sysroot/linux": "fuchsia/third_party/sysroot/linux"}
with open("gs.ensure", "w") as f:
    f.write("$ParanoidMode CheckPresence\n$OverrideInstallMode copy\n")
    for p, name in cipd.items():
        pkg = next(x for x in deps[p]["packages"]
                   if x["package"].replace("{{", "{").replace("}}", "}") == name)
        f.write(f"@Subdir sdk/{p}\n{name.replace('${platform}', 'linux-amd64')} {pkg['version']}\n")
gn = lambda v: str(v).lower() if isinstance(v, bool) else f'"{v}"'
with open(g["gclient_gn_args_file"], "w") as f:
    for k in g.get("gclient_gn_args", []):
        f.write(f"{k} = {gn(g['vars'][k])}\n")
PY
export -f shallow
xargs -P 8 -L 1 bash -c 'shallow "$0" "$1" "$2"' < git.list
cipd ensure -root "$W" -ensure-file gs.ensure

cd sdk
# target_os = ios solo para DART_TARGET_OS_*
git checkout -q runtime/BUILD.gn
python3 - <<'PY'
import re
p = "runtime/BUILD.gn"
s = open(p).read()
anchor = 'import("//build/config/sysroot.gni")\n'
assert anchor in s and 'config("dart_os_config")' in s
s = s.replace(anchor, anchor +
  '\ndeclare_args() {\n  dart_target_os_override = ""\n}\n'
  '_dart_target_os = target_os\n'
  'if (dart_target_os_override != "") {\n  _dart_target_os = dart_target_os_override\n}\n', 1)
s = re.sub(r'\btarget_os ==', '_dart_target_os ==', s)
s = s.replace('$target_os', '$_dart_target_os')
open(p, "w").write(s)
PY

OUT=out/ProductSIMARM64
python3 tools/gn.py --mode product --arch simarm64 --no-rbe
cat >> $OUT/args.gn <<'EOF'
dart_target_os_override = "ios"
dart_use_compressed_pointers = false
EOF
buildtools/gn gen $OUT
buildtools/ninja/ninja -C $OUT -j "$(nproc)" gen_snapshot
install -m 755 $OUT/exe.stripped/gen_snapshot "$OUTBIN"
"$OUTBIN" --version
