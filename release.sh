#!/bin/bash
# Un comando: mete el código, compila, firma, valida y —con --publish— sube.
#
#   bash /out/release.sh              compila y firma
#   bash /out/release.sh --publish    además sube a App Store Connect
set -uo pipefail
source /out/env.sh

PUBLISH=0
[ "${1:-}" = "--publish" ] && PUBLISH=1

step() { echo; echo "── $* ──"; }
t0=$(date +%s)

step "código"
bash /out/10-sync.sh || exit 1

VERSION=$(grep -m1 '^version:' "$APP/pubspec.yaml" | awk '{print $2}')
SHORT=${VERSION%%+*}
BUILD=${VERSION##*+}
echo ">> $NAME $SHORT (build $BUILD)"

# antes de gastar tres minutos: un build ya subido lo rechaza App Store Connect
if [ "$PUBLISH" = 1 ]; then
  step "App Store Connect"
  if ! BUNDLE=$BUNDLE python3 /out/50-asc.py --has "$BUILD"; then
    echo "el build $BUILD ya está subido; sube el número en pubspec.yaml"
    exit 1
  fi
  echo ">> build $BUILD libre"
fi

step "compilar y firmar"
bash /out/40-sign.sh || exit 1
IPA=$(ls -t "$APP"/build/ios/hatch/*-signed.ipa | head -1)

if [ "$PUBLISH" = 1 ]; then
  step "subir"
  hatch ios publish --ipa "$IPA" || exit 1
fi

echo
echo "$NAME $SHORT ($BUILD) en $(($(date +%s)-t0))s"
echo "$IPA"
[ "$PUBLISH" = 1 ] && echo "tarda unos minutos en aparecer en TestFlight"
exit 0
