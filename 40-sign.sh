#!/bin/bash
# Compila, firma y valida contra las comprobaciones de ingestión de Apple.
# No sube nada.
set -uo pipefail
source /out/env.sh
PW=${PW:-hatch}
SIG=/root/iospoc/signing
S=/out/signing

for f in dist.key dist.cer "$PROFILE" "$ASC_KEY"; do
  [ -f "$S/$f" ] || { echo "falta $S/$f"; exit 1; }
done

mkdir -p "$SIG"
cp -f "$S/$PROFILE" "$SIG/profile.mobileprovision"
cp -f "$S/$ASC_KEY" "$SIG/"

openssl pkcs12 -export -inkey "$S/dist.key" -in "$S/dist.cer" \
  -name "iPhone Distribution" -out "$SIG/cert.p12" -passout "pass:$PW" || exit 1
# algunas builds de rcodesign no leen el formato nuevo de OpenSSL 3
if ! /root/iospoc/rcodesign/rcodesign analyze-certificate --p12-file "$SIG/cert.p12" \
     --p12-password "$PW" >/dev/null 2>&1; then
  openssl pkcs12 -export -legacy -inkey "$S/dist.key" -in "$S/dist.cer" \
    -name "iPhone Distribution" -out "$SIG/cert.p12" -passout "pass:$PW" || exit 1
fi

python3 - <<PY
import json, os
p = os.path.expanduser("~/.hatch/ios.json")
os.makedirs(os.path.dirname(p), exist_ok=True)
cfg = json.load(open(p)) if os.path.exists(p) else {}
cfg["signing"] = {
    "p12_path": "$SIG/cert.p12",
    "p12_password": "$PW",
    "profile_path": "$SIG/profile.mobileprovision",
    "certificate_id": "$CERT_ID",
}
cfg["asc"] = {
    "issuer_id": "$ASC_ISSUER_ID",
    "key_id": "$ASC_KEY_ID",
    "p8_path": "$SIG/$ASC_KEY",
}
cfg["team_id"] = "$TEAM_ID"
json.dump(cfg, open(p, "w"), indent=2)
PY

cd "$APP" || exit 1
hatch ios build --bundle-id "$BUNDLE" --name "$NAME" --sign --distribution || exit 1

IPA=$(ls -t "$APP"/build/ios/hatch/*-signed.ipa 2>/dev/null | head -1)
[ -n "$IPA" ] || { echo "no se generó la .ipa firmada"; exit 1; }

hatch ios validate --ipa "$IPA" || exit 1
cp -f "$IPA" /out/out/
echo ">> $IPA"
