#!/bin/bash
# Entorno común a todos los pasos. Si solo una parte lo definiera, acabarías
# firmando algo distinto de lo que compilaste.
export PATH=/opt/flutter/bin:/root/iospoc/darwin-bin:/usr/local/bin:$PATH

[ -f /out/app.env ] || { echo "falta /out/app.env (copia app.env.example)"; exit 1; }
set -a
. /out/app.env
set +a

XC=/root/iospoc/xc/Toolchains/XcodeDefault.xctoolchain
export HATCH_IOS_SWIFT_COMPAT_DIR=$XC/usr/lib/swift/iphoneos
export HATCH_IOS_CLANG_RT_DIR=$XC/usr/lib/clang/17/lib/darwin
export HATCH_IOS_FB_DIR=/root/iospoc/fw/$NAME

# hatch lleva el MinimumOSVersion fijo; que siga a MIN_OS sin recordarlo
python3 /out/02-minos.py "${MIN_OS:-15.0}" >/dev/null

# hatch copia package_config.json al work dir sin absolutizar el rootUri del
# propio paquete, y entonces el frontend_server sale con 254
[ -f "$APP/.dart_tool/package_config.json" ] && python3 - "$APP" <<'PY'
import json, os, sys
p = os.path.join(sys.argv[1], ".dart_tool", "package_config.json")
d = json.load(open(p))
base = os.path.dirname(p)
for pkg in d["packages"]:
    ru = pkg.get("rootUri", "")
    if not ru.startswith("file:"):
        pkg["rootUri"] = "file://" + os.path.normpath(os.path.join(base, ru))
json.dump(d, open(p, "w"), indent=2)
PY
