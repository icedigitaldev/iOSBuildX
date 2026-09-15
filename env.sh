#!/bin/bash
# Entorno común a todos los pasos. Si solo una parte lo definiera, acabarías
# firmando algo distinto de lo que compilaste.
export PATH=/opt/flutter/bin:/root/iospoc/darwin-bin:/usr/local/bin:$PATH

[ -f /out/app.env ] || { echo "error: missing /out/app.env (see app.env.example)"; exit 1; }
set -a
. /out/app.env
set +a

XC=/root/iospoc/xc/Toolchains/XcodeDefault.xctoolchain
export HATCH_IOS_SWIFT_COMPAT_DIR=$XC/usr/lib/swift/iphoneos
export HATCH_IOS_CLANG_RT_DIR=$XC/usr/lib/clang/17/lib/darwin
export HATCH_IOS_FB_DIR=/root/iospoc/fw/$NAME

tidy() {
  sed -u -E \
    -e '/Woah! You appear to be trying to run flutter as root|superuser privileges|Sign later with:/d' \
    -e '/^(signing |entering nested bundle|leaving nested bundle|creating cryptographic signature|automatically |registering signing key|using time-stamp|setting entitlements|Frameworks\/[^ ]+\.framework$)/d' \
    -e '/^[[:space:]]*[-|\/]?[[:space:]]*(📎)?[[:space:]]*$/d'
}

# gen_snapshot con target iOS
GS_IOS=/out/vendor/gen_snapshot-ios
GS=/root/iospoc/engine/gs-linux/gen_snapshot
[ -f "$GS_IOS" ] || { echo "error: missing $GS_IOS (see 11-gensnapshot.sh)"; exit 1; }
DART_ENG=$(cat /root/iospoc/engine/dart-sdk/version 2>/dev/null)
DART_GS=$("$GS_IOS" --version 2>&1 | awk '{print $4}')
[ "$DART_ENG" = "$DART_GS" ] || {
  echo "error: gen_snapshot-ios targets Dart $DART_GS but the engine uses Dart $DART_ENG (rebuild with 11-gensnapshot.sh)"
  exit 1
}
cmp -s "$GS_IOS" "$GS" || install -m 755 "$GS_IOS" "$GS"

# frontend server con el registrante de plugins Dart
AOTRT=/root/iospoc/engine/dart-sdk/bin/dartaotruntime
[ "$(head -c 2 "$AOTRT")" = "#!" ] || mv -f "$AOTRT" "$AOTRT.real"
cmp -s /out/frontend_server.sh "$AOTRT" || install -m 755 /out/frontend_server.sh "$AOTRT"

# hatch lleva el MinimumOSVersion fijo; que siga a MIN_OS sin recordarlo
python3 /out/02-minos.py "${MIN_OS:-16.0}" >/dev/null

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
