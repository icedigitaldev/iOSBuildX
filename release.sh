#!/bin/bash
# Un comando: mete el código, compila, firma, valida y —con --publish— sube.
#
#   bash /out/release.sh              compila y firma
#   bash /out/release.sh --publish    además sube a App Store Connect
set -uo pipefail
source /out/env.sh

PUBLISH=0
[ "${1:-}" = "--publish" ] && PUBLISH=1

step() { echo; echo "==> $*"; }
t0=$(date +%s)

step "Sync sources"
bash /out/10-sync.sh || exit 1

VERSION=$(grep -m1 '^version:' "$APP/pubspec.yaml" | awk '{print $2}')
SHORT=${VERSION%%+*}
BUILD=${VERSION##*+}
echo "$NAME $SHORT ($BUILD)"

# antes de gastar tres minutos: un build ya subido lo rechaza App Store Connect
if [ "$PUBLISH" = 1 ]; then
  step "Check App Store Connect"
  if ! BUNDLE=$BUNDLE python3 /out/50-asc.py --has "$BUILD"; then
    echo "error: build $BUILD already exists in App Store Connect; increase the build number in pubspec.yaml"
    exit 1
  fi
  echo "build $BUILD is available"
fi

step "Build and sign"
bash /out/40-sign.sh || exit 1
IPA=$(ls -t "$APP"/build/ios/hatch/*-signed.ipa | head -1)

if [ "$PUBLISH" = 1 ]; then
  step "Upload"
  hatch ios publish --ipa "$IPA" 2>&1 | tidy || exit 1
fi

echo
echo "$NAME $SHORT ($BUILD) finished in $(($(date +%s)-t0))s"
echo "$IPA"
[ "$PUBLISH" = 1 ] && echo "uploaded; the build appears in TestFlight after App Store Connect processing"
exit 0
