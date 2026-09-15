#!/bin/bash
# Compila, estampa el SDK y el Xcode reales, firma y valida contra las comprobaciones
# de ingestión de Apple.
# No sube nada.
set -uo pipefail
source /out/env.sh
PW=${PW:-hatch}
SIG=/root/iospoc/signing
S=/out/signing

for f in dist.key dist.cer "$PROFILE" "$ASC_KEY"; do
  [ -f "$S/$f" ] || { echo "error: missing $S/$f"; exit 1; }
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
hatch ios build --bundle-id "$BUNDLE" --name "$NAME" 2>&1 | tidy || exit 1

UNSIGNED=$(ls -t "$APP"/build/ios/hatch/*.ipa 2>/dev/null | grep -v -- '-signed.ipa$' | head -1)
[ -n "$UNSIGNED" ] || { echo "error: no .ipa was produced"; exit 1; }
IPA="${UNSIGNED%.ipa}-signed.ipa"

# hatch estampa un SDK y un Xcode que no existen; se sustituyen por los reales antes
# de firmar. La firma es la misma que hace hatch: perfil dentro del bundle,
# entitlements del perfil y rcodesign sobre el .app entero.
WORK=$(mktemp -d)
unzip -oq "$UNSIGNED" -d "$WORK" || exit 1
BUNDLE_APP=$(ls -d "$WORK"/Payload/*.app | head -1)

python3 - "$BUNDLE_APP/Frameworks/App.framework/App" <<'PY' || exit 1
import sys
d = open(sys.argv[1], "rb").read()
i = d.find(b"\xf5\xf5\xdc\xdc")
feat = d[i + 52:i + 400].split(b"\0")[0].decode() if i >= 0 else ""
if " ios " not in f" {feat} " or " compressed-pointers" in f" {feat}":
    sys.exit(f"error: Dart snapshot is not an iOS snapshot: {feat}")
print("Dart snapshot:", feat)
PY
python3 /out/41-stamp.py "$BUNDLE_APP" /root/iospoc/iossdk/iPhoneOS26.2.sdk \
  /out/vendor/xcode-version.plist /out/vendor/macos-SystemVersion.plist || exit 1

cp -f "$SIG/profile.mobileprovision" "$BUNDLE_APP/embedded.mobileprovision"
openssl smime -inform DER -verify -noverify -in "$BUNDLE_APP/embedded.mobileprovision" \
  2>/dev/null > "$WORK/profile.plist" || exit 1
python3 - "$WORK" <<'PY'
import plistlib, sys
w = sys.argv[1]
ents = plistlib.load(open(w + "/profile.plist", "rb"))["Entitlements"]
plistlib.dump(ents, open(w + "/entitlements.plist", "wb"))
PY
/root/iospoc/rcodesign/rcodesign sign --p12-file "$SIG/cert.p12" --p12-password "$PW" \
  --entitlements-xml-file "$WORK/entitlements.plist" "$BUNDLE_APP" 2>&1 | tidy || exit 1
rm -f "$IPA"
( cd "$WORK" && zip -qX -r "$IPA" Payload ) || exit 1
rm -rf "$WORK"

hatch ios validate --ipa "$IPA" 2>&1 | tidy || exit 1
cp -f "$IPA" /out/out/
echo "signed: $IPA"
