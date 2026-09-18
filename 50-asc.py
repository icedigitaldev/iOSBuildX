#!/usr/bin/env python3
"""Qué versiones y builds hay ya en App Store Connect.

Un build subido no se puede borrar, solo caducar, y App Store Connect rechaza un
número repetido o menor: conviene mirar antes de elegir.

    python3 50-asc.py                 # lista todo
    python3 50-asc.py --has 21        # sale con 1 si el build 21 ya existe
    python3 50-asc.py --wait 21       # espera a que Apple lo procese

`--wait` existe porque subir no es publicar: Apple procesa despues, y a veces se
atasca sin avisar. Un build atascado **no aparece** en /builds —no es que salga
PROCESSING, es que no existe como recurso—, asi que esperar mirando la web es
esperar a ciegas. Sale con 0 en VALID, 1 si Apple lo rechazo, y 2 si se acabo el
plazo: ahi lo que toca es subir el siguiente numero, no seguir esperando.
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


# Cuanto se espera a que Apple procese, y cada cuanto se pregunta. Lo normal
# son 5-10 minutos; pasado el plazo lo que hay es un build atascado.
WAIT_MINUTES = int(os.environ.get("ASC_WAIT_MINUTES", "20"))
POLL_SECONDS = 30


def build_state(tok, app_id, version):
    """PROCESSING / VALID / INVALID / FAILED, o None si Apple aun no lo tiene.

    Que no este no es lo mismo que estar procesando: un build atascado nunca
    llega a ser recurso, y ese es justo el caso que hay que distinguir.
    """
    builds = get("/builds", tok, **{"filter[app]": app_id, "limit": "20"})["data"]
    for b in builds:
        if b["attributes"].get("version") == version:
            return b["attributes"].get("processingState") or "UNKNOWN"
    return None


def wait_for(tok, app_id, version):
    deadline = time.time() + WAIT_MINUTES * 60
    last = object()

    while True:
        state = build_state(tok, app_id, version)
        if state != last:
            print("   build %s: %s" % (version, state or "aun no aparece"), flush=True)
            last = state

        if state == "VALID":
            print("build %s procesado" % version)
            return 0
        if state in ("INVALID", "FAILED"):
            print("error: Apple rechazo el build %s (%s); mira el correo de "
                  "App Store Connect" % (version, state))
            return 1
        if time.time() >= deadline:
            print("error: Apple no proceso el build %s en %d min. Pasa: sube el "
                  "siguiente numero, no esperes mas. Un build no se puede borrar "
                  "ni reintentar con el mismo numero."
                  % (version, WAIT_MINUTES))
            return 2

        time.sleep(POLL_SECONDS)


def main():
    bundle = os.environ.get("BUNDLE")
    want_build = wait_build = None
    if "--has" in sys.argv:
        want_build = sys.argv[sys.argv.index("--has") + 1]
    elif "--wait" in sys.argv:
        wait_build = sys.argv[sys.argv.index("--wait") + 1]
    elif len(sys.argv) > 1:
        bundle = sys.argv[1]

    tok = token()
    apps = get("/apps", tok)["data"]
    if bundle:
        apps = [a for a in apps if a["attributes"]["bundleId"] == bundle]
    if not apps:
        sys.exit("error: no app with that bundle id in App Store Connect")

    for app in apps:
        builds = get("/builds", tok, **{"filter[app]": app["id"], "limit": "20"})["data"]
        if want_build:
            taken = [b for b in builds if b["attributes"].get("version") == want_build]
            sys.exit(1 if taken else 0)
        if wait_build:
            sys.exit(wait_for(tok, app["id"], wait_build))

        print("%s  (%s)" % (app["attributes"]["name"], app["attributes"]["bundleId"]))
        print("  App Store versions:")
        for v in get("/apps/%s/appStoreVersions" % app["id"], tok)["data"][:10]:
            a = v["attributes"]
            print("    %-10s %-22s %s" % (a["versionString"], a["appStoreState"],
                                          (a.get("createdDate") or "")[:10]))
        print("  builds:")
        for b in builds:
            a = b["attributes"]
            print("    %-8s %-12s %s" % (a.get("version"), a.get("processingState"),
                                         (a.get("uploadedDate") or "")[:16]))
        if not builds:
            print("    (none)")


main()
