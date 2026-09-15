#!/bin/bash
# Compila una app Flutter a .ipa sin firmar.
#   APP=/root/MiApp NAME=MiApp BUNDLE=com.ejemplo.miapp bash /out/30-build.sh
set -uo pipefail
source /out/env.sh

cd "$APP" || exit 1
t0=$(date +%s)
hatch ios build --bundle-id "$BUNDLE" --name "$NAME" > /out/out/build.log 2>&1
rc=$?
echo "exit code $rc, $(($(date +%s)-t0))s"
tail -25 /out/out/build.log
exit $rc
