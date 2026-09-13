#!/usr/bin/env python3
"""Qué versiones y builds hay ya en App Store Connect.

Un build subido no se puede borrar, solo caducar, y App Store Connect rechaza un
número repetido o menor: conviene mirar antes de elegir.

    python3 50-asc.py                 # lista todo
    python3 50-asc.py --has 21        # sale con 1 si el build 21 ya existe
"""
import json, os, sys, time, urllib.error, urllib.request

import jwt  # PyJWT

API = "https://api.appstoreconnect.apple.com/v1"
HATCH_CFG = os.path.expanduser("~/.hatch/ios.json")
APP_ENV = "/out/app.env"
SIGNING = "/out/signing"


def credentials():
    """De ~/.hatch/ios.json si ya se firmó alguna vez; si no, de app.env."""
    if os.path.exists(HATCH_CFG):
        c = json.load(open(HATCH_CFG))["asc"]
        return c["issuer_id"], c["key_id"], c["p8_path"]
    env = dict(l.split("#")[0].strip().split("=", 1)
               for l in open(APP_ENV) if "=" in l.split("#")[0])
    return (env["ASC_ISSUER_ID"], env["ASC_KEY_ID"],
            os.path.join(SIGNING, env["ASC_KEY"]))


def token():
    issuer, key_id, p8 = credentials()
    now = int(time.time())
    return jwt.encode(
        {"iss": issuer, "iat": now, "exp": now + 20 * 60, "aud": "appstoreconnect-v1"},
        open(p8).read(), algorithm="ES256", headers={"kid": key_id, "typ": "JWT"})


def get(path, tok, **params):
    url = API + path + ("?" + "&".join("%s=%s" % kv for kv in params.items()) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        sys.exit("%s -> %s\n%s" % (url, e.code, e.read().decode()[:400]))


def main():
    bundle = os.environ.get("BUNDLE")
    want_build = None
    if "--has" in sys.argv:
        want_build = sys.argv[sys.argv.index("--has") + 1]
    elif len(sys.argv) > 1:
        bundle = sys.argv[1]

    tok = token()
    apps = get("/apps", tok)["data"]
    if bundle:
        apps = [a for a in apps if a["attributes"]["bundleId"] == bundle]
    if not apps:
        sys.exit("no hay ninguna app con ese bundle id en App Store Connect")

    for app in apps:
        builds = get("/builds", tok, **{"filter[app]": app["id"], "limit": "20"})["data"]
        if want_build:
            taken = [b for b in builds if b["attributes"].get("version") == want_build]
            sys.exit(1 if taken else 0)

        print("%s  (%s)" % (app["attributes"]["name"], app["attributes"]["bundleId"]))
        print("  versiones publicadas:")
        for v in get("/apps/%s/appStoreVersions" % app["id"], tok)["data"][:10]:
            a = v["attributes"]
            print("    %-10s %-22s %s" % (a["versionString"], a["appStoreState"],
                                          (a.get("createdDate") or "")[:10]))
        print("  builds subidos:")
        for b in builds:
            a = b["attributes"]
            print("    %-8s %-12s %s" % (a.get("version"), a.get("processingState"),
                                         (a.get("uploadedDate") or "")[:16]))
        if not builds:
            print("    (ninguno)")


main()
